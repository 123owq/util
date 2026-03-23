import asyncio
from playwright.async_api import async_playwright
import re

async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print("1. KIPRIS 접속 중...")
        await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="networkidle")
        
        # 팝업 닫기 시도
        try:
            await page.click("#mainPopup .btn-close", timeout=2000)
            print("   - 팝업 닫기 성공")
        except:
            print("   - 팝업 없음 또는 닫기 실패")

        print("2. 'AP=[120120550993]' 검색 중...")
        await page.fill("#inputQuery", "AP=[120120550993]")
        await page.click("button.btn-search")
        
        # 결과 로딩 대기 (충분히)
        print("3. 결과 로딩 대기 중...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3) # 추가 여유 시간
        
        # 현재 페이지의 모든 버튼 확인 (디버깅용)
        buttons = await page.locator("button.link.under").all()
        print(f"4. 발견된 'button.link.under' 개수: {len(buttons)}개")
        
        # 만약 버튼이 없다면 다른 셀렉터 시도
        if len(buttons) == 0:
            print("   - [주의] 기존 셀렉터로 버튼을 찾을 수 없음. 대체 셀렉터 시도...")
            links = await page.locator("a").all()
            print(f"   - 전체 <a> 태그 개수: {len(links)}개")
            # 상세 페이지 링크 패턴 확인 (예: openDetail)
            for i, link in enumerate(links[:50]): # 상위 50개만 확인
                txt = await link.inner_text()
                href = await link.get_attribute("href")
                onclick = await link.get_attribute("onclick")
                if onclick and "openDetail" in onclick:
                    print(f"   - [발견!] onclick 패턴: {onclick}")

        # 스크린샷 저장 (구조 확인용)
        await page.screenshot(path="kipris_diag.png")
        print("5. 진단 스크린샷 저장 완료: kipris_diag.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
