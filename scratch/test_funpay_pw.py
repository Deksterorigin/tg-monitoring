import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://funpay.com/lots/73/")
        await page.wait_for_timeout(2000)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        item = soup.select_one('.tc-item')
        if item:
            print(item.prettify())
        else:
            print("Not found")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
