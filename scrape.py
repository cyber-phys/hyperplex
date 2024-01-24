import requests
import lxml.html

tld = "https://leginfo.legislature.ca.gov"
url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"

def scrape_links(url):
    response = requests.get(url)
    tree = lxml.html.fromstring(response.content)
    for a_tag in tree.xpath('//*[@id="codestocheader"]//a'):
        link_url = a_tag.get('href')
        text = a_tag.text_content().strip()
        print(f"URL: {link_url}, \nText: {text}\n")
        scrape_links(tld + link_url)
    for a_tag in tree.xpath('//*[@id="codestreeForm2"]//a'):
        link_url = a_tag.get('href')
        text = a_tag.text_content().strip()
        print(f"URL: {link_url}, \nText: {text}\n")
        scrape_links(tld + link_url)
    for a_tag in tree.xpath('//*[@id="expandedbranchcodesid"]//a'):
        link_url = a_tag.get('href')
        text = a_tag.text_content().strip()
        print(f"URL: {link_url}, \nText: {text}\n")
        scrape_links(tld + link_url)
    for law_sections in tree.xpath('//*[@id="manylawsections"]'):
        text = law_sections.text_content().strip()
        print(text)

scrape_links(url)