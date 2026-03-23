import asyncio
from playwright.async_api import async_playwright

async def debug_html():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0')
        page = await context.new_page()
        
        print("1. 검색 페이지 접속...")
        await page.goto("https://www.kipris.or.kr/kpat/searchLogina.do", wait_until="domcontentloaded")
        await asyncio.sleep(2) # JS 렌더링 대기
        
        # 모든 입력창(input) 정보 출력
        print("2. 모든 <input> 요소 조사:")
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(el => ({
                id: el.id,
                name: el.name,
                class: el.className,
                type: el.type,
                placeholder: el.placeholder
            }));
        }""")
        for i in inputs:
            print(f"   - {i}")

        # 모든 버튼(button) 정보 출력
        print("3. 모든 <button> 요소 조사:")
        buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).map(el => ({
                id: el.id,
                class: el.className,
                text: el.innerText.trim()
            }));
        }""")
        for b in buttons:
            print(f"   - {b}")

        # Iframe 확인
        iframes = await page.frames
        print(f"4. 발견된 프레임(iframe) 개수: {len(iframes)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_html())
