import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import os
import sys

# Configure logging towrite to a file
log_filename = 'scrape_log.log'
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_filename, 'a', 'utf-8')])
# Initialize Chrome options for Selenium
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")

visited_links = set()
law_section_links = set()
law_section_links_lock = threading.Lock()

def display_timer(stop_event, law_section_links, law_section_links_lock, url):
    """Displays elapsed time and the current number of entries in law_section_links until the stop_event is set."""
    start_time = time.time()
    while not stop_event.is_set():
        elapsed_time = time.time() - start_time
        formatted_time = f"{elapsed_time:5.2f} seconds"
        with law_section_links_lock:  # Use the lock to safely access law_section_links
            links_count = len(law_section_links)
        # Clear the console
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"Scraping URL: {url}\nElapsed Time: {formatted_time} | Law Section Links: {links_count}", end="")
        sys.stdout.flush()
        time.sleep(1)

def setup_driver():
    """Creates and returns a Selenium WebDriver with predefined options."""
    logging.debug("Setting up driver")
    return webdriver.Chrome(options=chrome_options)

def extract_links(driver, xpath):
    """Extracts and returns links from the given XPath within the provided driver's current page."""
    try:
        logging.debug(f"Extracting links with XPath: {xpath}")
        elements = driver.find_elements(By.XPATH, xpath)
        return [element.get_attribute("href") for element in elements]
    except Exception as e:
        logging.error(f"Error extracting links: {e}")
        return []

def cali_scrape_codedisplayexpand(url):
    logging.info(f"Scraping URL: {url}")
    driver = setup_driver()
    driver.get(url)
    expanded_links = []
    manylaw_links = []

    # Extract links from the 'expandedbranchcodesid' section
    expanded_links += extract_links(driver, "//*[@id='expandedbranchcodesid']//a")

    # Check if 'manylawsections' is present and add the current URL if so
    if driver.find_elements(By.ID, "manylawsections"):
        manylaw_links.append(url)

    driver.quit()
    return list(set(expanded_links)), manylaw_links  # Ensure uniqueness

def cali_scrape(url):
    global visited_links
    global law_section_links
    urls_to_scrape = [url]

    # Start the timer thread
    stop_event = threading.Event()
    timer_thread = threading.Thread(target=display_timer, args=(stop_event, law_section_links, law_section_links_lock, url))
    timer_thread.start()

    with ThreadPoolExecutor(max_workers=10) as executor:
        while urls_to_scrape:
            logging.debug("Starting new batch of URLs to scrape")
            futures = {executor.submit(cali_scrape_codedisplayexpand, url): url for url in urls_to_scrape}
            urls_to_scrape = []

            for future in as_completed(futures):
                expanded_links, manylaw_links = future.result()
                with law_section_links_lock:
                    law_section_links.update(set(filter(lambda href: href not in law_section_links, manylaw_links)))
                new_links = list(filter(lambda href: href not in visited_links, expanded_links))
                visited_links.update(new_links)
                urls_to_scrape.extend(new_links)

    # Stop the timer thread
    stop_event.set()
    timer_thread.join()

    logging.info("Scraping done")
    logging.info(f"Law section links: {law_section_links}")

# Example usage
cali_scrape("https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=BPC")