import asyncio
from playwright.async_api import async_playwright

async def inspect_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print("1. 검색 페이지 접속...")
        await page.goto("https://www.kipris.or.kr/kpat/searchLogina.do", wait_until="domcontentloaded")
        
        # 입력창 후보 확인
        print("2. 주요 입력창 및 버튼 확인 중...")
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input, button')).map(el => ({
                tag: el.tagName,
                id: el.id,
                name: el.name,
                class: el.className,
                type: el.type,
                value: el.value || el.innerText
            })).filter(el => el.id.includes('Query') || el.class.includes('search') || el.id.includes('search'));
        }""")
        for item in inputs:
            print(f"   - {item}")

        # 검색 시도 (가장 유력한 후보 사용)
        print("3. 검색 시도...")
        try:
            # 1순위: #inputQuery / 2순위: #queryText
            target_input = "#inputQuery" if await page.locator("#inputQuery").count() > 0 else "#queryText"
            print(f"   - 타겟 입력창: {target_input}")
            await page.fill(target_input, "AP=[120120550993]")
            
            # 검색 버튼 (가장 유력한 폼 제출 버튼)
            await page.keyboard.press("Enter")
            print("   - Enter 키 입력으로 검색 시도")
            
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)
            
            # 결과 확인
            res_count = await page.locator("button.link.under").count()
            print(f"4. 결과 링크 개수: {res_count}개")
            
            if res_count == 0:
                print("   - [분석] 링크가 여전히 0개입니다. 전체 HTML 요약:")
                body_snippet = await page.evaluate("document.body.innerText.substring(0, 500)")
                print(f"   - Body 텍스트 일부: {body_snippet}")

        except Exception as e:
            print(f"   - 오류 발생: {e}")

        await page.screenshot(path="kipris_inspect.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_page())
