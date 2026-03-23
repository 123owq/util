import asyncio
from playwright.async_api import async_playwright

async def final_inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0')
        page = await context.new_page()
        
        print("1. 검색 페이지 접속...")
        await page.goto("https://www.kipris.or.kr/kpat/searchLogina.do", wait_until="domcontentloaded")
        
        # 1. 입력창 찾기 및 검색어 입력
        print("2. 검색어 입력 시도 (#queryText)...")
        if await page.locator("#queryText").count() > 0:
            await page.fill("#queryText", "AP=[120120550993]")
        else:
            print("   - #queryText를 찾을 수 없음!")
            
        # 2. 검색 버튼들 전수 조사 (onclick에 search가 들어간 버튼)
        print("3. 검색 버튼 후보 추출...")
        candidates = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, a, input[type="button"]')).map(el => ({
                tag: el.tagName,
                id: el.id,
                class: el.className,
                text: (el.innerText || el.value || "").trim(),
                onclick: el.getAttribute('onclick') || ""
            })).filter(el => el.onclick.toLowerCase().includes('search') || el.text.includes('검색'));
        }""")
        for c in candidates:
            print(f"   - [후보] {c}")

        # 3. 첫 번째 검색 버튼 클릭 시도
        if candidates:
            target = candidates[0]
            print(f"4. 검색 실행: [{target['text']}] 클릭...")
            await page.locator(f"{target['tag'].lower()}:has-text('{target['text']}')").first.click(force=True)
        else:
            print("4. 검색 버튼을 찾지 못해 Enter 키 시도...")
            await page.keyboard.press("Enter")

        # 4. 결과 대기 및 스크린샷
        await asyncio.sleep(5)
        print(f"5. 현재 페이지 URL: {page.url}")
        
        # 결과 링크가 있는지 확인
        links = await page.locator("button.link.under").count()
        print(f"6. 결과 링크(button.link.under) 개수: {links}개")
        
        if links == 0:
            # 다른 종류의 링크 확인
            other_links = await page.locator(".search_result_list a").count()
            print(f"   - .search_result_list 내 <a> 개수: {other_links}개")

        await page.screenshot(path="final_inspect.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(final_inspect())
