import urllib.request
from bs4 import BeautifulSoup

url = 'https://funpay.com/lots/736/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')
soup = BeautifulSoup(html, 'html.parser')
item = soup.select_one('.tc-item')
print(item.prettify() if item else 'Not found')
