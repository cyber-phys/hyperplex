import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import sys
import signal
from functools import partial
import threading

class SeleniumScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.chrome_options = self.setup_chrome_options()
        self.visited_links = set()
        self.law_section_links = set()
        self.processed_manylaw_links = set()
        self.executor = ThreadPoolExecutor(max_workers=50)
        self.manylaw_executor = ThreadPoolExecutor(max_workers=10)
        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self.signal_handler)

    @staticmethod
    def setup_chrome_options():
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        return chrome_options

    def signal_handler(self, sig, frame):
        print('\nQuickly exiting...')
        self.stop_event.set()
        self.executor.shutdown(wait=False)

    def setup_driver(self):
        logging.debug("Setting up driver")
        return webdriver.Chrome(options=self.chrome_options)

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
        driver = self.setup_driver()
        driver.get(url)
        element = driver.find_element(By.ID, "manylawsections")
        elements = element.find_elements(By.TAG_NAME, 'a')
        for link in elements:
            href = link.get_attribute("href")
            # if href not in self.visited_links:
            print(link.get_attribute("href"))
            driver.execute_script("arguments[0].click();", link)
            e = driver.find_element(By.ID, "codeLawSectionNoHead")
            top_level_divs = e.find_elements(By.XPATH, "./div")
            for div in top_level_divs:
                text_transform_value = div.value_of_css_property("text-transform")
                text_indent_value = div.value_of_css_property("text-indent")
                display_value = div.value_of_css_property("display")
                if text_transform_value == "uppercase":
                    print(f"Title: {div.text}")
                elif (text_indent_value != "0px"):
                    print(f"Division: {div.text}")
                elif (display_value == "inline"):
                    print(f"Chapter: {div.text}")
                else:
                    part = div.find_element(By.TAG_NAME,"h6")
                    law = div.find_element(By.TAG_NAME, "p")
                    print(f"Part: {part.text}")
                    print(f"Law: {law.text}")
        driver.quit()

    def scrape_url(self, url):
        if self.stop_event.is_set():
            return set(), set()
        
        logging.info(f"Scraping URL: {url}")
        driver = self.setup_driver()
        driver.get(url)
        expanded_links = self.extract_links(driver, "//*[@id='expandedbranchcodesid']//a")
        manylaw_links = {url} if driver.find_elements(By.ID, "manylawsections") else set()
        driver.quit()
        return expanded_links, manylaw_links
    
    def display_timer(self, url):
        # Print the static part of the message once, outside the loop
        print(f"Press ctl+c to exit... Scraping URL: {url}")
        start_time = time.time()
        while not self.stop_event.is_set():
            elapsed_time = time.time() - start_time
            formatted_time = f"{elapsed_time:5.2f} seconds"
            links_count = len(self.law_section_links)
            # Clear the dynamic content line using ANSI escape code and update it
            # This assumes the cursor is already on the line to be cleared
            print(f"\r\033[KElapsed Time: {formatted_time} | Law Section Links: {links_count}", end="")
            time.sleep(1)
        # Ensure there's a newline at the end when the loop exits
        print()

    def start_scraping(self):
        urls_to_scrape = [self.base_url]
        timer_thread = threading.Thread(target=partial(self.display_timer, self.base_url))
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
        print("Scraping completed")
        print(self.law_section_links)
        logging.info("Scraping done")
        logging.info(f"Law section links: {self.law_section_links}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler('scrape_log.log', 'a', 'utf-8')])
    scraper = SeleniumScraper("https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=BPC")
    scraper.start_scraping()