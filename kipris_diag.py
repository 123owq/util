import asyncio
from playwright.async_api import async_playwright

async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print("1. KIPRIS 특허 검색 페이지로 직접 접속...")
        # 홈 대신 검색 페이지로 바로 접속하여 팝업 방해 최소화
        await page.goto("https://www.kipris.or.kr/kpat/searchLogina.do", wait_until="domcontentloaded")
        
        # 모든 팝업 및 방해 요소 강제 숨김 처리 (JS 주입)
        print("2. 방해 요소(팝업 등) 제거 중...")
        await page.add_style_tag(content="""
            #mainPopup, .popup-dim, .divPopup, #divPopup { display: none !important; }
        """)
        
        try:
            # 검색어 입력
            print("3. 검색어 입력: AP=[120120550993]")
            await page.fill("#inputQuery", "AP=[120120550993]")
            
            # 검색 버튼 클릭 (force=True로 가려져 있어도 강제 클릭)
            # 여러 버튼 중 실제 동작하는 버튼을 특정하기 위해 클래스 조합 사용
            search_btn = page.locator("button.btn-search").first
            await search_btn.click(force=True)
            print("   - 검색 실행 완료")
        except Exception as e:
            print(f"   - 검색 실행 중 오류: {e}")

        # 결과 로딩 대기
        print("4. 결과 로딩 대기...")
        try:
            # 검색 결과 리스트가 나타날 때까지 대기
            await page.wait_for_selector("section.search_result_list", timeout=15000)
            print("   - 결과 리스트 확인됨!")
        except:
            print("   - 결과 리스트 대기 시간 초과. (검색 방식 확인 필요)")

        # 현재 상태 확인을 위한 정보 수집
        all_buttons = await page.locator("button.link.under").all()
        print(f"5. 발견된 특허 링크(button.link.under) 개수: {len(all_buttons)}개")
        
        for btn in all_buttons[:3]:
            txt = await btn.inner_text()
            onclick = await btn.get_attribute("onclick")
            print(f"   - 특허: {txt[:20]}... | onclick: {onclick}")

        await page.screenshot(path="kipris_diag_v2.png")
        print("6. 진단 스크린샷 저장 완료: kipris_diag_v2.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
