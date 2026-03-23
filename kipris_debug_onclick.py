import asyncio
from playwright.async_api import async_playwright
import time

async def run(playwright):
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        accept_downloads=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    )
    page = await context.new_page()

    await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="domcontentloaded")
    time.sleep(2)
    
    # JS로 팝업 침 (버튼 클릭 아님)
    await page.evaluate("() => { const p = document.getElementById('mainPopup'); if(p) p.style.display='none'; }")
    
    await page.fill("#inputQuery", "AP=[120120550993]")
    time.sleep(0.5)
    # 정확한 검색 버튼 (KIPRIS 폼 내부의 submit 버튼)
    await page.evaluate("document.querySelector('button.btn-search').click()")
    
    print("Waiting 5 seconds for results...")
    time.sleep(5)
    
    # Count all buttons
    all_buttons = await page.locator("button").all()
    print(f"Total <button> elements: {len(all_buttons)}")
    
    link_under = await page.locator("button.link.under").all()
    print(f"button.link.under count: {len(link_under)}")
    
    # Print onclick of first 5
    for i, btn in enumerate(link_under[:5]):
        oc = await btn.get_attribute("onclick")
        txt = await btn.inner_text()
        print(f"  [{i}] onclick={oc!r} text={txt[:40]!r}")
    
    # Also dump page URL
    print(f"Current URL: {page.url}")
    
    await browser.close()

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
