import requests
import lxml.html
import uuid
from markdownify import markdownify
from db import connect_db, execute_sql, create_database
import sqlite3
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

tld = "https://leginfo.legislature.ca.gov"
url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"
db_file = 'law_database_feb21.db'

visited_db_file = 'visited_urls.db'  # Name of the new database file

def create_visited_urls_database(db_path):
    """
    Creates a new SQLite database to store visited URLs.

    Parameters:
    - db_path (str): The file path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visited_urls (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL UNIQUE
            visited BOOLEAN NOT NULL,
            no_more_links BOOLEAN NOT NULL
        );
    ''')
    conn.commit()
    conn.close()

def insert_visited_url(db_path, url):
    """
    Inserts a visited URL into the visited_urls table.

    Parameters:
    - db_path (str): The file path to the SQLite database.
    - url (str): The URL that has been visited.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO visited_urls (url) VALUES (?);', (url,))
        conn.commit()
    except sqlite3.IntegrityError:
        # URL already exists in the table, ignore the error
        pass
    finally:
        conn.close()

def check_visited_url(db_path, url):
    """
    Checks if a URL has already been visited.

    Parameters:
    - db_path (str): The file path to the SQLite database.
    - url (str): The URL to check.

    Returns:
    - bool: True if the URL has been visited, False otherwise.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM visited_urls WHERE url = ?;', (url,))
    visited = cursor.fetchone()
    conn.close()
    return bool(visited)

def insert_law_entry(db_file, code, section, text, amended, url):
    """
    Inserts a new law entry into the law_entries table in the SQLite database.

    Parameters:
    - db_path (str): The file path to the SQLite database.
    - code (str): The code name associated with the law entry.
    - section (str): The section number of the law entry.
    - text (str): The text content of the law entry, converted to Markdown format.
    - amended (str): Information about when the law was last amended.
    - url (str): The URL to the original law entry source.

    This function generates a unique UUID for each new entry, constructs an SQL
    insert statement, and executes it using a database connection obtained from
    the connect_db function. It commits the changes and closes the connection.
    """
    # Connect to the SQLite3 database using the connect_db function
    conn = connect_db(db_file)
    
    if conn is not None:
        # Generate a unique UUID for the new entry
        entry_uuid = str(uuid.uuid4())
        
        # SQL statement to insert a new row
        insert_row_sql = """
        INSERT INTO law_entries (uuid, code, section, text, amended, url)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        
        # Execute the SQL statement using execute_sql function
        execute_sql(conn, insert_row_sql, (entry_uuid, code, section, text, amended, url), commit=True)
        
        conn.close()

def scrape_links(url):
    """
    Scrapes law entries from a given URL and inserts them into a database.

    This function navigates through the law sections on the provided URL, extracts
    relevant information such as code name, section number, and the law text, and
    inserts each entry into the database. It recursively processes links found within
    the page to ensure comprehensive coverage of all related law entries.

    Parameters:
    - url (str): The URL to start scraping from.

    The function defines two inner functions, `process_links` and `get_code_name`,
    to assist in processing individual links and extracting the code name from the
    page structure, respectively.
    """
    def find_links(xpath):
        for a_tag in tree.xpath(xpath):
            link_url = a_tag.get('href')
            full_url = tld + link_url

    def process_links(xpath):
        """
        Processes each link found at the given XPath by recursively scraping its target.

        Parameters:
        - xpath (str): The XPath expression used to find links on the page.
        """
        for a_tag in tree.xpath(xpath):
            link_url = a_tag.get('href')
            full_url = tld + link_url
            text = a_tag.text_content().strip()
            print(f"URL: {link_url}, \nText: {text}\n")
            if full_url != url:
                scrape_links(full_url)

    response = requests.get(url)
    tree = lxml.html.fromstring(response.content)

    def get_code_name(xpath):
        """
        Extracts the code name from the specified XPath location.

        Parameters:
        - xpath (str): The XPath expression used to locate the code name on the page.

        Returns:
        - str: The extracted code name.
        """
        # Find the <div> with the id 'manylawsections'
        manylawsections_div = tree.xpath(xpath)[0]
        b_tags_text = ""

        # Iterate over all elements in the manylawsections <div>
        for element in manylawsections_div.iterdescendants():
            if element.tag == 'a':
                # Stop if an <a> tag is found
                break
            if element.tag == 'b':
                # Add the text content of <b> tag to the string
                b_tags_text += "\n" + element.text_content().strip()

        return b_tags_text.strip()
        
    # Process many law sections
    for law_sections in tree.xpath('//*[@id="manylawsections"]/*/*/*/h6/a'):
        code_name = get_code_name('//*[@id="manylawsections"]')
        section_number = law_sections.text_content().strip()
        prev_div = law_sections.getparent().getparent()
        # Select all <p> tags within prev_div
        p_tags = prev_div.xpath('.//p')
        # Convert each <p> tag to a string of raw HTML
        p_html_list = []
        for p in p_tags:
            # Find all <i> tags within the current <p> tag
            i_tags = p.xpath('.//i')
            if len(i_tags) > 1:
                raise ValueError("More than one <i> tag found within a <p> tag.")
            elif i_tags:
                # Save content of the single <i> tag
                i_content = i_tags[0].text_content().strip()
                # Remove the <i> tag from the tree
                i_tags[0].drop_tree()
            # Convert the <p> tag to a string of raw HTML
            p_html_list.append(lxml.html.tostring(p, encoding='unicode').strip())

        # Join all the HTML strings from the <p> tags
        prev_div_html = ''.join(p_html_list) if p_tags else "No <p> tags found"
        markdown_content = markdownify(prev_div_html)
        # print(markdown_content)
        insert_law_entry(db_file, code_name, section_number, markdown_content, i_content, url)
        print(f"Code: {code_name}, Section: {section_number}")
    
    # Process each group of links with the same structure
    process_links('//*[@id="codestocheader"]//a')
    process_links('//*[@id="codestreeForm2"]//a')
    process_links('//*[@id="expandedbranchcodesid"]//a')


## Find all links on page and add them to todo_scrape list:
## Navigate to each link:
## Find all links on the page (sometimes links will lead to same place as source)
## Keep going until all links have been traverced

## h4 no ident is the code
## h4 with ident is the division
## h5 is the devision heading (chapter)
## h6 is the section number
## p is the law text 

## codes_to_list
## expandedbranchcodesid
def cali_expand_scrape(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Enables headless mode
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model, required in some environments
    chrome_options.add_argument("--disable-gpu")  # Applicable only to windows os
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems

    driver = webdriver.Chrome(options=chrome_options)
    # Create a new instance of the Chrome driver
    # driver = webdriver.Chrome(options=chrome_options)

    # Navigate to the page
    driver.get(url)
    print(url)
    try:
        expandedbranchcodesid = driver.find_element(By.XPATH, "//*[@id='expandedbranchcodesid']")
        if expandedbranchcodesid:
            links = expandedbranchcodesid.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute("href")
                print(href)
                if href not in visted_links:
                    visted_links.append(href)
                    cali_expand_scrape(href)
                else:
                    print(f"href in visted_links: {href}")
    except Exception as e:
        print("no div id=expandedbranchcodesid:", e)

    try:
        manylawsections = driver.find_element(By.ID, "manylawsections")
        if manylawsections:
            elements = manylawsections.find_elements(By.TAG_NAME, 'a')
            # Print the href attributes of the extracted links
            num_elements = len(elements)

            for i in range(num_elements):
                # Navigate to the page
                driver.get(url)
                # Find the element with the JavaScript-based URL
                element = driver.find_element(By.ID, "manylawsections")
                elements = element.find_elements(By.TAG_NAME, 'a')
                for link in elements:
                    href = link.get_attribute("href")
                    if href not in visted_links:
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
                        # print(e.text)
                        visted_links.append(href)
                        break
                    else:
                        print(f"href in visted_links: {href}")
    except Exception as e:
        print("no div id=manylawsections:", e)


def test_js_parse(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Enables headless mode
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model, required in some environments
    chrome_options.add_argument("--disable-gpu")  # Applicable only to windows os
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems

    driver = webdriver.Chrome(options=chrome_options)
    # Create a new instance of the Chrome driver
    # driver = webdriver.Chrome(options=chrome_options)

    # Navigate to the page
    driver.get(url)
    # Find the element with the JavaScript-based URL
    try:
        codes_toc_list = driver.find_element(By.ID, 'codestreeFrom2')
        if codes_toc_list:
            links = element.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute("href")
                if href not in visted_links:
                    visted_links.append(href)
                    test_js_parse(tld + href)
    except:
        print("no div id=codestreeFrom2")

    try:
        expandedbranchcodesid = driver.find_element(By.ID, "expandedbranchcodesid")
        if expandedbranchcodesid:
            links = element.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute("href")
                if href not in visted_links:
                    visted_links.append(href)
                    print(f"Going to link {href}")
                    test_js_parse(tld + href)
    except:
        print("no div id=expandedbranchcodesid")

    manylawsections = driver.find_element(By.ID, "manylawsections")
    if manylawsections:
        elements = manylawsections.find_elements(By.TAG_NAME, 'a')
        # Print the href attributes of the extracted links
        num_elements = len(elements)

        for i in range(num_elements):
            # Navigate to the page
            driver.get(url)
            # Find the element with the JavaScript-based URL
            element = driver.find_element(By.ID, "manylawsections")
            elements = element.find_elements(By.TAG_NAME, 'a')
            for link in elements:
                href = link.get_attribute("href")
                if href not in visted_links:
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
                    # print(e.text)
                    visted_links.append(href)
                    break

def get_sections():
    tld = "https://leginfo.legislature.ca.gov"
    sections_url = "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml"
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Enables headless mode
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model, required in some environments
    chrome_options.add_argument("--disable-gpu")  # Applicable only to windows os
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems

    driver = webdriver.Chrome(options=chrome_options)

    # Navigate to the list of sections
    driver.get(sections_url)
    try:
        sections_div = driver.find_element(By.ID, 'codestocheader')
        if sections_div:
            links = element.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute("href")
                test_js_parse(tld + href)
    except:
        print("no div id=codestocheader")
    


    # # Extract the JavaScript function and its arguments
    # js_function = element.get_attribute('href')
    # args = js_function.split("(")[1].split(")")[0].split(",")

    # # Execute the JavaScript function to fetch the final URL
    # final_url = driver.execute_script(f"return submitCodesValues({args[0]},{args[1]},{args[2]},{args[3]},{args[4]},{args[5]})")

    # Print the final URL
    # print(final_url)
        # response = requests.get(url)
    # tree = lxml.html.fromstring(response.content)
    # print(tree)
    # hrefs = tree.xpath('//a/@href')
    # print(hrefs)
    # for href in hrefs:
    #     if href.startswith('javascript:'):
    #         # Extract parameters from the JavaScript function call
    #         params = re.findall(r"'(.*?)'", href)
    #         # Process the parameters as needed
    #         # For example, print the parameters
    #         print(params)

# create_visited_urls_database(visited_db_file)
# create_database(db_file)
# scrape_links(url)

# test_js_parse("https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=FGC&division=0.5.&title=&part=&chapter=1.&article=")
visted_links = []
# test_js_parse("https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV&heading2=PRELIMINARY%20PROVISIONS")
# test_js_parse("https://leginfo.legislature.ca.gov/faces/codesTOCSelected.xhtml?tocCode=CIV&tocTitle=+Civil+Code+-+CIV")
# get_sections()
cali_expand_scrape("https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=BPC")