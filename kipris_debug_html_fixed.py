import asyncio
from playwright.async_api import async_playwright

async def fix_debug_html():
    async with async_playwright() as p:
        # 실제 브라우저와 거의 동일한 옵션 설정
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print("1. KIPRIS 검색 페이지 접속...")
        try:
            # 네트워크 대기 시간을 넉넉히 주어 로딩 확인
            await page.goto("https://www.kipris.or.kr/kpat/searchLogina.do", wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"   - 접속 중 타임아웃/오류: {e}")
        
        # 전체 텍스트 내용 일부 확인 (로딩 여부 판단)
        content = await page.content()
        print(f"2. 페이지 내용 길이: {len(content)} 자")
        if len(content) < 500:
            print(f"   - [경고] 페이지 내용이 너무 적습니다: {content}")
        else:
            print(f"   - 페이지 내용 (앞부분 200자): {content[:200]}")

        # 모든 <input> 다시 조사
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(el => ({
                id: el.id, name: el.name, type: el.type
            }));
        }""")
        print(f"3. <input> 개수: {len(inputs)}")
        for i in inputs[:10]:
            print(f"   - {i}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(fix_debug_html())
