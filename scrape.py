import requests
import lxml.html

url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"
response = requests.get(url)

# Parse the HTML content with lxml
tree = lxml.html.fromstring(response.content)

# Find all anchor tags and print their href attribute and text content
for a_tag in tree.xpath('//a'):
    url = a_tag.get('href')
    text = a_tag.text_content().strip()
    print(f"URL: {url}, Text: {text}")
