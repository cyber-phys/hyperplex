import requests
import lxml.html
import uuid
from markdownify import markdownify
from db import connect_db, execute_sql, create_database

tld = "https://leginfo.legislature.ca.gov"
url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"
db_file = 'law_database_test.db'

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

create_database(db_file)
scrape_links(url)