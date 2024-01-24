import requests
import lxml.html
from markdownify import markdownify

tld = "https://leginfo.legislature.ca.gov"
url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"

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

    # Process many law sections
    for law_sections in tree.xpath('//*[@id="manylawsections"]/*/*/*/h6/a'):
        text = law_sections.text_content().strip()
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
        print(markdown_content)
        prev_div_text = prev_div.text_content().strip() if prev_div else "No preceding div"
        # print(f"Section Text: {text}, Previous Div Text: {prev_div_text}")
    
    # Process each group of links with the same structure
    process_links('//*[@id="codestocheader"]//a')
    process_links('//*[@id="codestreeForm2"]//a')
    process_links('//*[@id="expandedbranchcodesid"]//a')
    # process_links('//*[@id="manylawsections"]//a')
    


    #  # Process singal law sections
    # for law_sections in tree.xpath('//*[@id="single_law_section"]'):
    #     text = law_sections.text_content().strip()
        # print(text)

scrape_links(url)