import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import signal
from functools import partial
import threading
from queue import Queue
from selenium import webdriver
from threading import Semaphore
import db
import uuid
from datetime import datetime
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import argparse
from selenium.webdriver import Chrome

class CustomWebDriver(Chrome):
    """
    CustomWebDriver extends the functionality of the Selenium Chrome WebDriver.
    
    This class provides additional methods for robust web scraping, such as the ability
    to safely navigate to URLs with retry logic in case of page load failures.
    
    Attributes:
        Inherits all attributes from the Selenium Chrome WebDriver class.
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initializes the CustomWebDriver with the given arguments.
        
        Args:
            *args: Variable length argument list to pass to the Chrome WebDriver.
            **kwargs: Arbitrary keyword arguments to pass to the Chrome WebDriver.
        """
        chrome_options = self.setup_chrome_options()
        super().__init__(*args, options=chrome_options, **kwargs)

    @staticmethod
    def setup_chrome_options():
        """
        Sets up the Chrome options for the CustomWebDriver instance.

        Returns:
            Options: A configured Options instance with arguments for headless operation and other settings.
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        return chrome_options

    def safe_get(self, url, attempts=5, backoff=5):
        """
        Attempts to navigate to a URL using a Selenium WebDriver. If the page load times out,
        it retries the operation, backing off for a specified amount of time between attempts.
        
        Args:
            url (str): The URL to navigate to.
            attempts (int): The maximum number of attempts to make. Default is 5.
            backoff (int): The amount of time (in seconds) to wait before retrying after a timeout. Default is 5 seconds.
        
        Raises:
            Exception: If the navigation fails after the specified number of attempts.
        """
        current_attempt = 1
        while current_attempt <= attempts:
            try:
                self.get(url)
                return  # If successful, exit the function
            except Exception as e:
                if current_attempt > 3:
                    print(f"Attempt {current_attempt} failed with error: {e}")
                if current_attempt == attempts:
                    raise  # Reraise the last exception if out of attempts
                current_attempt += 1
                time.sleep(backoff)  # Wait before retrying

class WebDriverPool:
    def __init__(self, max_size=100):
        """
        Initializes a pool of Selenium WebDriver instances.

        Parameters:
        - max_size (int): The maximum number of WebDriver instances in the pool.
        """
        self.available_drivers = Queue(maxsize=max_size)
        self.semaphore = Semaphore(max_size)
        for _ in range(max_size):
            self.available_drivers.put(self.create_driver())

    def create_driver(self):
        """
        Creates a new CustomWebDriver instance.

        Returns:
            CustomWebDriver: A new instance of CustomWebDriver.
        """
        return CustomWebDriver()

    def get_driver(self):
        """
        Retrieves an available WebDriver instance from the pool.

        Returns:
        - WebDriver: An available WebDriver instance.
        """
        self.semaphore.acquire()
        return self.available_drivers.get()

    def release_driver(self, driver):
        """
        Returns a WebDriver instance back to the pool.

        Parameters:
        - driver (WebDriver): The WebDriver instance to be returned to the pool.
        """
        self.available_drivers.put(driver)
        self.semaphore.release()
    
    def quit_all_drivers(self):
        """
        Quits all WebDriver instances in the pool and closes all associated browser windows.
        """
        while not self.available_drivers.empty():
            driver = self.available_drivers.get()
            driver.quit()
    
    def get_all_drivers(self):
        """
        Retrieves a list of all WebDriver instances currently in the pool.

        Returns:
        - List[WebDriver]: A list of WebDriver instances.
        """
        return list(self.available_drivers.queue)
    
class SeleniumScraper:
    def __init__(self, db_file, jurisdiction):
        self.base_urls = []
        self.visited_links = set()
        self.law_section_links = set()
        self.processed_manylaw_links = set()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.manylaw_executor = ThreadPoolExecutor(max_workers=1)
        self.stop_event = threading.Event()
        self.driver_pool = WebDriverPool(max_size=200)
        self.db_file = db_file
        self.n_entries_added = 0
        self.n_entries_lock = threading.Lock()
        self.jurisdiction = jurisdiction
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print('\nQuickly exiting...')
        self.stop_event.set()
        self.executor.shutdown(wait=False)
        self.driver_pool.quit_all_drivers()

    def insert_law_entry(self, db_file, result):
        """
        Inserts a new law entry into the law_entries table in the SQLite database.
        Also populates the law_structure table with hierarchical data.

        Parameters:
        - db_file (str): The file path to the SQLite database.
        - result (dict): A dictionary containing all the fields for the law entry.
        """
        try:
            conn = db.connect_db(db_file)
            
            if conn is not None:
                # Check if the entry already exists based on the URL
                check_sql = "SELECT url, text FROM law_entries WHERE url = ? AND text = ? LIMIT 1"
                existing_entry = db.execute_sql(conn, check_sql, (result['URL'], result['Law']), fetchone=True)
                
                if existing_entry:
                    existing_url, existing_text = existing_entry
                    logging.error(f"\nError: Duplicate entry with text '{result['Law'][:30]}...'\nCurrent URL: {result['URL']}\nDB Match URL: {existing_url}\n")
                else:
                    # Generate a unique UUID for the new entry
                    law_entry_uuid = str(uuid.uuid4())
                    
                    insert_row_sql = """
                    INSERT INTO law_entries (uuid, text, url, creation_time)
                    VALUES (?, ?, ?, datetime('now'));
                    """
                    
                    # Prepare the data tuple from the result dictionary
                    law_entry_tuple = (
                        law_entry_uuid,
                        result['Law'],
                        result['URL'],
                    )
                    
                    # Execute the SQL statement to insert the law entry
                    db.execute_sql(conn, insert_row_sql, law_entry_tuple, commit=True)
                    with self.n_entries_lock:
                        self.n_entries_added += 1

                    # Insert hierarchical data into law_structure
                    hierarchy = ['Jurisdiction', 'Code', 'Division', 'Part', 'Title', 'Chapter', 'Article', 'Provision', 'Section']
                    parent_uuid = None  # Initialize parent_uuid for the top level
                    for level in hierarchy:
                        if result.get(level):
                            structure_uuid = str(uuid.uuid4())
                            insert_structure_sql = """
                            INSERT INTO law_structure (uuid, type, text, text_italic, child_uuid, law_uuid)
                            VALUES (?, ?, ?, ?, ?, ?);
                            """
                            structure_tuple = (
                                structure_uuid,
                                level.lower(),  # Convert to lowercase to match the 'type' CHECK constraint
                                result[level],
                                result.get(f"{level}_italic", ""),
                                parent_uuid,  # This will be NULL for the top level
                                law_entry_uuid,
                            )
                            db.execute_sql(conn, insert_structure_sql, structure_tuple, commit=True)
                            parent_uuid = structure_uuid  # Update parent_uuid for the next level

                conn.close()
        except Exception as e:
            print(f"\nError with db write: {e}")

    def extract_links(self, driver, xpath):
        try:
            logging.debug(f"Extracting links with XPath: {xpath}")
            elements = driver.find_elements(By.XPATH, xpath)
            return {element.get_attribute("href") for element in elements}
        except Exception as e:
            logging.error(f"Error extracting links: {e}")
            return set()
        
    def scrape_manylawsections(self, url):
        logging.info(f"Scraping manylawsections at URL: {url}")
        driver = self.driver_pool.get_driver()
        try:
            driver.safe_get(url)
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.ID, "manylawsections")))
            element = driver.find_element(By.ID, "manylawsections")
            elements = element.find_elements(By.TAG_NAME, 'a')
            
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = [executor.submit(self.process_link, link.get_attribute("href"), url) for link in elements]
                for future in as_completed(futures):
                    result = future.result()
                    self.insert_law_entry(self.db_file, result)
        except Exception as e:
            logging.error(f"Exception in scrape_manylawsections for URL {url}: {e}")
            print(f"retrying url: {url}")
            # TODO we should handel this better
            self.scrape_manylawsections(url)
        finally:
            self.driver_pool.release_driver(driver)
            logging.info(f"Finished scrape_manylawsections for URL: {url}")

    def process_link(self, link, url):
        """Process a single link and return details as a dictionary."""
        driver = self.driver_pool.get_driver()
        try:
            driver.safe_get(url)
            js_code = link.split(":", 1)[1] if ":" in link else link
            driver.execute_script(js_code)
            current_url = driver.current_url
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.ID, "codeLawSectionNoHead")))
            e = driver.find_element(By.ID, "codeLawSectionNoHead")
            top_level_divs = e.find_elements(By.XPATH, "./div")
            result = {"Jurisdiction": self.jurisdiction,
                      "Code": None,
                      "Division": None,
                      "Division_italic": None,
                      "Title": None, 
                      "Title_italic": None,
                      "Part": None,
                      "Part_italic": None,
                      "Chapter": None,
                      "Chapter_italic": None,
                      "Article": None,
                      "Article_italic": None,
                      "Section": None,
                      "Provisions": None,
                      "Provisions_italic": None,
                      "Section": None,
                      "Section_italic": None,
                      "Law": None,
                      "Law_italic": None,
                      "URL": current_url}
            for div in top_level_divs:
                text_transform_value = div.value_of_css_property("text-transform")
                text_indent_value = div.value_of_css_property("text-indent")
                display_value = div.value_of_css_property("display")
                if text_transform_value == "uppercase":
                    result["Code"] = div.text
                elif text_indent_value != "0px" or display_value == "inline":
                    if div.text.startswith("TITLE"):
                        result["Title"] = div.find_element(By.TAG_NAME, "b").text
                        result["Title_italic"] = div.find_element(By.TAG_NAME, "i").text
                    elif div.text.startswith("DIVISION"):
                        result["Division"] = div.find_element(By.TAG_NAME, "b").text
                        result["Division_italic"] = div.find_element(By.TAG_NAME, "i").text
                    elif div.text.startswith("PART"):
                        result["Part"] = div.find_element(By.TAG_NAME, "b").text
                        result["Part_italic"] = div.find_element(By.TAG_NAME, "i").text
                    elif div.text.startswith("CHAPTER"):
                        result["Chapter"] = div.find_element(By.TAG_NAME, "b").text
                        result["Chapter_italic"] = div.find_element(By.TAG_NAME, "i").text
                    elif div.text.startswith("ARTICLE"):
                        result["Article"] = div.find_element(By.TAG_NAME, "b").text
                        result["Article_italic"] = div.find_element(By.TAG_NAME, "i").text
                    elif div.text.startswith("GENERAL PROVISIONS") or div.text.startswith("PROVISIONS"):
                        result["Provisions"] = div.find_element(By.TAG_NAME, "b").text
                        result["Provisions_italic"] = div.find_element(By.TAG_NAME, "i").text
                    else:
                        print(f"Error can't figure out subsection label: {div.text}")
                else:
                    section = div.find_element(By.TAG_NAME, "h6").text
                    section_italic = div.find_element(By.TAG_NAME, "i").text
                    law_p = div.find_elements(By.TAG_NAME, "p")
                    result["Section"] = section
                    result["Section_italic"] = section_italic
                    law = ''
                    for law_i, paragraph in enumerate(law_p):
                        if law_i == 0:
                            law = paragraph.text
                        else:
                            law += "\n" + paragraph.text
                    if law != '':
                        result["Law"] = law
                    else:
                        print(f"ERROR law is blank for url: {current_url}\n")
        except Exception as e:
            logging.error(f"Exception in process_url for Url: {url}: {e}")
            logging.error(f"Exception in process_url for Link: {current_url}: {e}")
        finally:
            self.driver_pool.release_driver(driver)
        return result

    def scrape_url(self, url):
        if self.stop_event.is_set():
            return set(), set()
        
        logging.info(f"Scraping URL: {url}")
        driver = self.driver_pool.get_driver()
        try:
            driver.safe_get(url)
            expanded_links = self.extract_links(driver, "//*[@id='expandedbranchcodesid']//a")
            manylaw_links = {url} if driver.find_elements(By.ID, "manylawsections") else set()
        finally:
            self.driver_pool.release_driver(driver)
        return expanded_links, manylaw_links
    
    ## For Ohio we have to expand a list of links to the law until we finally get to the law
    def scrape_url_ohio(self, url):
        if self.stop_event.is_set():
            return set()        
        
        logging.info(f"Scraping URL: {url}")
        driver = self.driver_pool.get_driver()
        law_links = set()
        result = {}
        try:
            driver.safe_get(url)
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CLASS_NAME, "laws-table")))
            lawTable = driver.find_element(By.CLASS_NAME, "laws-table")
            lawTableLinks = lawTable.find_elements(By.TAG_NAME, 'a')
            for link in lawTableLinks:
                h = link.get_attribute("href")
                if h:
                    law_links.add(h)
                else:
                    logging.error(f"Error NO LINK found at url: {url}")
        except Exception as e1:
            print(f"No such element: {url}")
            try:
                result = {"Jurisdiction": self.jurisdiction,
                      "Code": None,
                      "Division": None,
                      "Division_italic": None,
                      "Title": None, 
                      "Title_italic": None,
                      "Part": None,
                      "Part_italic": None,
                      "Chapter": None,
                      "Chapter_italic": None,
                      "Article": None,
                      "Article_italic": None,
                      "Section": None,
                      "Provisions": None,
                      "Provisions_italic": None,
                      "Section": None,
                      "Section_italic": None,
                      "Law": None,
                      "Law_italic": None,
                      "URL": url}
                # WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CLASS_NAME, "laws-body")))
                logging.info(f"Processing URL: {url}")
                lawHeader = driver.find_element(By.CLASS_NAME, "laws-header")
                lawBody = driver.find_element(By.CLASS_NAME, "laws-body")
                section = lawHeader.find_element(By.TAG_NAME, "h1").text
                logging.info(f"Section: {section}")
                result["Section"] = section
                result["Section_italic"] = ""
                # result["Section_italic"] = lawBody.find_element(By.CLASS_NAME, "laws-notice").text
                law_p = lawBody.find_elements(By.TAG_NAME, "p")
                law_text = ""
                for breadcrumb in lawHeader.find_elements(By.CLASS_NAME, "breadcrumbs-node"):
                    if breadcrumb.text.startswith("Ohio Revised Code"):
                        result["Code"] = breadcrumb.text
                        logging.info(f"Code: {breadcrumb.text}")
                    elif breadcrumb.text.startswith("Ohio Constitution"):
                        result["Code"] = breadcrumb.text
                        logging.info(f"Code: {breadcrumb.text}")
                    elif breadcrumb.text.startswith("Ohio Administrative Code"):
                        result["Code"] = breadcrumb.text
                        logging.info(f"Code: {breadcrumb.text}")
                    elif breadcrumb.text.startswith("Title"):
                        result["Title"] = breadcrumb.text
                        result["Title_italic"] = ""
                        logging.info(f"Title: {breadcrumb.text}")
                    elif breadcrumb.text.startswith("Chapter"):
                        result["Chapter"] = breadcrumb.text
                        result["Chapter_italic"] = ""
                        logging.info(f"Chapter: {breadcrumb.text}")
                    elif breadcrumb.text.startswith("Article"):
                        result["Article"] = breadcrumb.text
                        result["Article_italic"] = ""
                        logging.info(f"Article: {breadcrumb.text}")
                for law_i, paragraph in enumerate(law_p):   
                    logging.info(f"Law: {paragraph.text}")                 
                    if law_i == 0:
                        law_text = paragraph.text
                    else:
                        law_text += "\n" + paragraph.text
                result["Law"] = law_text
                self.insert_law_entry(self.db_file, result)
            except Exception as e2:
                print("\n" + url + "\n")
                logging.error(f"Error {url} {e2}")
        finally:
            self.driver_pool.release_driver(driver)
        return law_links
    
    def display_timer(self, state):
        # Print the static part of the message once, outside the loop
        print(f"Press ctl+c to exit... Scraping {state} code")
        start_time = time.time()
        while not self.stop_event.is_set():
            elapsed_time = time.time() - start_time
            formatted_time = f"{elapsed_time:5.2f} seconds"
            links_count = len(self.law_section_links)
            with self.n_entries_lock:
                n_entries = self.n_entries_added
            # Clear the dynamic content line using ANSI escape code and update it
            # This assumes the cursor is already on the line to be cleared
            print(f"\r\033[KElapsed Time: {formatted_time} | Law Section Links: {links_count} | Entries Added: {n_entries}", end="")
            time.sleep(1)
        # Ensure there's a newline at the end when the loop exits
        print()

    def start_scraping(self):
        self.base_urls = ["https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=CIV",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=BPC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=CCP",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=COM",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=CORP",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=EDC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=ELEC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=EVID",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=FAM",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=FIN",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=FGC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=FAC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=GOV",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=HNC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=HSC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=INS",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=LAB",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=MVC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=PEN",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=PROB",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=PCC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=PRC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=PUC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=RTC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=SHC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=UIC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=VEH",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=WAT",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=WIC",
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=CONS"]
        urls_to_scrape = self.base_urls
        timer_thread = threading.Thread(target=partial(self.display_timer, "California"))
        timer_thread.start()

        manylaw_futures = set()

        while urls_to_scrape:
            futures = {self.executor.submit(self.scrape_url, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links, manylaw_links = future.result()
                self.law_section_links.update(manylaw_links - self.law_section_links)
                new_links = expanded_links - self.visited_links
                self.visited_links.update(new_links)
                urls_to_scrape.extend(new_links)

                for manylaw_link in manylaw_links:
                    if manylaw_link not in self.processed_manylaw_links:
                        manylaw_future = self.manylaw_executor.submit(self.scrape_manylawsections, manylaw_link)
                        manylaw_futures.add(manylaw_future) 
                        self.processed_manylaw_links.add(manylaw_link)

        # Check if any future is still running
        while not self.stop_event.is_set():
            # Get the count of futures that are not done
            running_tasks = [f for f in manylaw_futures if not f.done()]
            if not running_tasks:
                break  # Exit the loop if no tasks are running
            logging.info(f"Waiting for {len(running_tasks)} tasks to complete...")
            for i, task in enumerate(running_tasks, start=1):
                logging.debug(f"Task {i}/{len(running_tasks)} is still running.")
            time.sleep(1)  # Wait for a bit before checking again

        logging.info("All tasks have been completed.")
        self.manylaw_executor.shutdown(wait=True)
        timer_thread.join()
        self.stop_event.set()
        print("\nScraping completed")
        logging.info("Scraping done")
        logging.info(f"Law section links: {self.law_section_links}")

    def start_scraping_ohio(self):
        self.jurisdiction = "OH"
        self.base_urls = ["https://codes.ohio.gov/ohio-constitution"]

        urls_to_scrape = self.base_urls
        timer_thread = threading.Thread(target=partial(self.display_timer, "Ohio"))
        timer_thread.start()

        while urls_to_scrape:
            futures = {self.executor.submit(self.scrape_url_ohio, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links = future.result()
                new_links = expanded_links - self.visited_links
                self.visited_links.update(new_links)
                urls_to_scrape.extend(new_links)
        
        self.base_urls = ["https://codes.ohio.gov/ohio-revised-code"]
        urls_to_scrape = self.base_urls

        while urls_to_scrape:
            futures = {self.executor.submit(self.scrape_url_ohio, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links = future.result()
                new_links = expanded_links - self.visited_links
                self.visited_links.update(new_links)
                urls_to_scrape.extend(new_links)
        
        self.base_urls = ["https://codes.ohio.gov/ohio-administrative-code"]
        urls_to_scrape = self.base_urls

        while urls_to_scrape:
            futures = {self.executor.submit(self.scrape_url_ohio, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links = future.result()
                new_links = expanded_links - self.visited_links
                self.visited_links.update(new_links)
                urls_to_scrape.extend(new_links)


        logging.info("All tasks have been completed.")
        timer_thread.join()
        self.stop_event.set()
        print("\nScraping completed")
        logging.info("Scraping done")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the web scraper for different jurisdictions.')
    parser.add_argument('--state', choices=['CA', 'OH'], required=True, help='The state to scrape: CA for California or OH for Ohio')
    args = parser.parse_args()

    log_file_name = f"scrape_log_{args.state}_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.log"
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler(log_file_name, 'a', 'utf-8')])

    db_file = f"law_{args.state}_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.db"
    jurisdiction = args.state
    db.create_database(db_file)

    scraper = SeleniumScraper(db_file, jurisdiction)
    
    if jurisdiction == "CA":
        scraper.start_scraping()
    elif jurisdiction == "OH":
        scraper.start_scraping_ohio()