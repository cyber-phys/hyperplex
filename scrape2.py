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

class WebDriverPool:
    def __init__(self, max_size=100):
        self.available_drivers = Queue(maxsize=max_size)
        self.semaphore = Semaphore(max_size)
        self.chrome_options = self.setup_chrome_options()
        for _ in range(max_size):
            self.available_drivers.put(self.create_driver())

    @staticmethod
    def setup_chrome_options():
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        return chrome_options

    def create_driver(self):
        return webdriver.Chrome(options=self.chrome_options)

    def get_driver(self):
        self.semaphore.acquire()
        return self.available_drivers.get()

    def release_driver(self, driver):
        self.available_drivers.put(driver)
        self.semaphore.release()
    
    def quit_all_drivers(self):
        while not self.available_drivers.empty():
            driver = self.available_drivers.get()
            driver.quit()

class SeleniumScraper:
    def __init__(self, base_urls, db_file):
        self.base_urls = base_urls
        self.visited_links = set()
        self.law_section_links = set()
        self.processed_manylaw_links = set()
        self.executor = ThreadPoolExecutor(max_workers=50)
        self.manylaw_executor = ThreadPoolExecutor(max_workers=5)
        self.stop_event = threading.Event()
        self.driver_pool = WebDriverPool(max_size=100)
        self.db_file = db_file
        self.n_entries_added = 0
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print('\nQuickly exiting...')
        self.stop_event.set()
        self.executor.shutdown(wait=False)
        self.driver_pool.quit_all_drivers()

    def insert_law_entry(self, db_file, code, section, text, amended, url):
        """
        Inserts a new law entry into the law_entries table in the SQLite database if an entry with the same text does not already exist.
        If a duplicate text entry is found, prints an error message instead of inserting.

        Parameters:
        - db_path (str): The file path to the SQLite database.
        - code (str): The code name associated with the law entry.
        - section (str): The section number of the law entry.
        - text (str): The text content of the law entry, converted to Markdown format.
        - amended (str): Information about when the law was last amended.
        - url (str): The URL to the original law entry source.
        """
        # Connect to the SQLite3 database using the connect_db function
        try:
            conn = db.connect_db(db_file)
            
            if conn is not None:
                # Check for existing entry with the same text
                check_sql = "SELECT EXISTS(SELECT 1 FROM law_entries WHERE text = ? LIMIT 1)"
                exists = db.execute_sql(conn, check_sql, (text,), fetchone=True)[0]
                
                if exists:
                    print(f"\nError: Duplicate entry with text '{text[:30]}...\nDuplicate URL: {url}' found. Skipping insertion.")
                else:
                    # Generate a unique UUID for the new entry
                    entry_uuid = str(uuid.uuid4())
                    
                    # SQL statement to insert a new row
                    insert_row_sql = """
                    INSERT INTO law_entries (uuid, code, section, text, amended, url)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """
                    
                    # Execute the SQL statement using execute_sql function
                    db.execute_sql(conn, insert_row_sql, (entry_uuid, code, section, text, amended, url), commit=True)
                    self.n_entries_added += 1

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
            driver.get(url)
            element = driver.find_element(By.ID, "manylawsections")
            elements = element.find_elements(By.TAG_NAME, 'a')
            
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(self.process_link, link.get_attribute("href"), url) for link in elements]
                for future in as_completed(futures):
                    result = future.result()
                    # print(result)
                    self.insert_law_entry(self.db_file, result['Title'], result['Division'], result['Law'], "none", result['URL'])
        finally:
            self.driver_pool.release_driver(driver)

    def process_link(self, link, url):
        """Process a single link and return details as a dictionary."""
        driver = self.driver_pool.get_driver()
        try:
            driver.get(url)
            js_code = link.split(":", 1)[1] if ":" in link else link
            driver.execute_script(js_code)
            current_url = driver.current_url
            e = driver.find_element(By.ID, "codeLawSectionNoHead")
            top_level_divs = e.find_elements(By.XPATH, "./div")
            result = {"Title": "", "Division": "", "Chapter": "", "Part": "", "Law": "", "URL": current_url}
            for div in top_level_divs:
                text_transform_value = div.value_of_css_property("text-transform")
                text_indent_value = div.value_of_css_property("text-indent")
                display_value = div.value_of_css_property("display")
                if text_transform_value == "uppercase":
                    result["Title"] = div.text
                elif text_indent_value != "0px":
                    result["Division"] = div.text
                elif display_value == "inline":
                    result["Chapter"] = div.text
                else:
                    part = div.find_element(By.TAG_NAME, "h6").text
                    law = div.find_element(By.TAG_NAME, "p").text
                    result["Part"] = part
                    result["Law"] = law
        finally:
            self.driver_pool.release_driver(driver)
        return result

    def scrape_url(self, url):
        if self.stop_event.is_set():
            return set(), set()
        
        logging.info(f"Scraping URL: {url}")
        driver = self.driver_pool.get_driver()
        try:
            driver.get(url)
            expanded_links = self.extract_links(driver, "//*[@id='expandedbranchcodesid']//a")
            manylaw_links = {url} if driver.find_elements(By.ID, "manylawsections") else set()
        finally:
            self.driver_pool.release_driver(driver)
        return expanded_links, manylaw_links
    
    def display_timer(self, state):
        # Print the static part of the message once, outside the loop
        print(f"Press ctl+c to exit... Scraping {state} code")
        start_time = time.time()
        while not self.stop_event.is_set():
            elapsed_time = time.time() - start_time
            formatted_time = f"{elapsed_time:5.2f} seconds"
            links_count = len(self.law_section_links)
            n_entries = self.n_entries_added
            # Clear the dynamic content line using ANSI escape code and update it
            # This assumes the cursor is already on the line to be cleared
            print(f"\r\033[KElapsed Time: {formatted_time} | Law Section Links: {links_count} | Entries Added: {n_entries}", end="")
            time.sleep(1)
        # Ensure there's a newline at the end when the loop exits
        print()

    def start_scraping(self):
        urls_to_scrape = self.base_urls
        timer_thread = threading.Thread(target=partial(self.display_timer, "California"))
        timer_thread.start()

        while urls_to_scrape:
            futures = {self.executor.submit(self.scrape_url, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links, manylaw_links = future.result()
                self.law_section_links.update(manylaw_links - self.law_section_links)
                new_links = expanded_links - self.visited_links
                self.visited_links.update(new_links)
                urls_to_scrape.extend(new_links)

                links_to_remove = set()
                for manylaw_link in manylaw_links:
                    if manylaw_link not in self.processed_manylaw_links:
                        self.manylaw_executor.submit(self.scrape_manylawsections, manylaw_link)
                        self.processed_manylaw_links.add(manylaw_link)
                        links_to_remove.add(manylaw_link)

                manylaw_links -= links_to_remove

        self.stop_event.set()
        timer_thread.join()
        self.manylaw_executor.shutdown(wait=True)
        print("\nScraping completed")
        logging.info("Scraping done")
        logging.info(f"Law section links: {self.law_section_links}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler('scrape_log.log', 'a', 'utf-8')])
    db_file = "test.db"
    db.create_database(db_file)
    urls = ["https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=CIV",
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
    scraper = SeleniumScraper(urls, db_file)
    scraper.start_scraping()