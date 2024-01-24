import requests
import lxml.html
import sqlite3
import uuid
from markdownify import markdownify

tld = "https://leginfo.legislature.ca.gov"
url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"
db_path = 'law_database.db'

def create_law_entries_table(db_path):
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # SQL statement to create the table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS law_entries (
        uuid TEXT PRIMARY KEY,
        code TEXT,
        section REAL,
        text TEXT,
        amended TEXT,
        url TEXT
    );
    """
    
    # Execute the SQL statement
    cursor.execute(create_table_sql)
    
    # Commit the changes and close the connection
    conn.commit()
    conn.close()

def insert_law_entry(db_path, code, section, text, amended, url):
    # Connect to the SQLite3 database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Generate a unique UUID for the new entry
    entry_uuid = str(uuid.uuid4())
    
    # SQL statement to insert a new row
    insert_row_sql = """
    INSERT INTO law_entries (uuid, code, section, text, amended, url)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    
    # Execute the SQL statement
    cursor.execute(insert_row_sql, (entry_uuid, code, section, text, amended, url))
    
    # Commit the changes and close the connection
    conn.commit()
    conn.close()

def scrape_links(url):
    def process_links(xpath):
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
        insert_law_entry(db_path, code_name, section_number, markdown_content, i_content, url)
        print(f"Code: {code_name}, Section: {section_number}")
    
    # Process each group of links with the same structure
    process_links('//*[@id="codestocheader"]//a')
    process_links('//*[@id="codestreeForm2"]//a')
    process_links('//*[@id="expandedbranchcodesid"]//a')

create_law_entries_table(db_path)
scrape_links(url)