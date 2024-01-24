import requests
from bs4 import BeautifulSoup

url = "https://leginfo.legislature.ca.gov/faces/codes.xhtml"
response = requests.get(url)

# Create a BeautifulSoup object with the response content
soup = BeautifulSoup(response.content, 'html.parser')

# Find all anchor tags and print their href attribute and text content
for a_tag in soup.find_all('a'):
    url = a_tag.get('href')
    text = a_tag.get_text(strip=True)
    print(f"URL: {url}, Text: {text}")
