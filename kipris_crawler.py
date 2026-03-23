import asyncio
from playwright.async_api import async_playwright, expect
import time
import os

async def run(playwright):
    # headless=False 로 설정하여 브라우저가 직접 움직이는 것을 볼 수 있게 합니다.
    browser = await playwright.chromium.launch(headless=False) 
    context = await browser.new_context(
        accept_downloads=True, # PDF 다운로드를 위해 필수
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    )
    page = await context.new_page()

    print("1. KIPRIS 메인 페이지로 이동 중...")
    await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="networkidle")

    print("2. AP=[120120550993] 검색 중...")
    await page.fill("#inputQuery", "AP=[120120550993]")
    await page.click("button.btn-search")
    
    # 검색 결과 목록 로딩 대기
    await page.wait_for_selector("button.link.under")
    print("3. 검색 결과 로딩 완료.")
    
    # 첫 번째 특허 클릭하기 (오버레이 팝업 띄우기)
    print("4. 첫 번째 특허 상세 정보 오버레이 여는 중...")
    await page.locator("button.link.under").first.click()
    
    # 오버레이 내용 로딩 대기
    await page.wait_for_selector(".detail-tab-body")
    time.sleep(2) # 렌더링 안정화를 위해 잠시 대기
    
    # '통합행정정보' 탭 클릭
    print("5. '통합행정정보' 탭 접근 중...")
    await page.locator("button.btn-tab", has_text="통합행정정보").click()
    
    # 통합행정정보 안의 테이블 데이터가 로드될 때까지 대기
    await page.wait_for_selector(".detail-tab-body table", state="visible")
    time.sleep(3) # AJAX 로딩 시간 확보 (충분히 주는 것이 좋습니다)
    
    print("6. '의견제출서' 또는 '보정서' 항목 스캔 시작...")
    rows = await page.locator(".detail-tab-body table tbody tr").all()
    
    os.makedirs('kipris_downloads', exist_ok=True)
    
    found_docs = 0
    for row in rows:
        text = await row.inner_text()
        # 해당 행에 의견/보정서가 있는지 텍스트 매칭
        if "의견제출서" in text or "보정서" in text:
            print(f"> 문서 발견: {text.strip().replace(chr(10), ' ')}")
            
            # js 함수를 실행하는 다운로드 버튼 (돋보기 아이콘 등)
            btn = row.locator("a.btn-blank").first
            if await btn.is_visible():
                print("  => 다운로드를 시도합니다...")
                
                try:
                    # 클릭과 동시에 다운로드 이벤트를 기다림
                    async with page.expect_download(timeout=60000) as download_info:
                        # 클릭 수행 (일부 js 경고창이나 새 창을 띄울 수 있으므로 주의)
                        await btn.click()
                    
                    download = await download_info.value
                    
                    # 다운로드 파일 저장
                    file_path = os.path.join("kipris_downloads", download.suggested_filename)
                    await download.save_as(file_path)
                    print(f"  => 다운로드 완료: {file_path}")
                    found_docs += 1
                    
                    # 연속 다운로드 시 IP 차단 방지를 위한 휴식
                    print("  => 서버 공격 방지를 위해 5초 대기...")
                    time.sleep(5)
                except Exception as e:
                    print(f"  => 다운로드 중 에러 발생: {e}")
                
    if found_docs == 0:
        print("이 특허에는 '의견제출서'나 '보정서'가 없거나 다운로드할 버튼이 없습니다.")
        
    print("모든 작업 완료. 브라우저를 종료합니다.")
    await context.close()
    await browser.close()

async def main():
    try:
        async with async_playwright() as playwright:
            await run(playwright)
    except Exception as e:
        print(f"시스템 에러 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
