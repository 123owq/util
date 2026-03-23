import asyncio
from playwright.async_api import async_playwright
import time
import os
import re

async def run(playwright):
    browser = await playwright.chromium.launch(headless=False) 
    context = await browser.new_context(
        accept_downloads=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    )
    page = await context.new_page()

    print("1. KIPRIS 사이트 접속 중...")
    await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="networkidle")

    # 메인 페이지의 공지 팝업만 조심스럽게 제거 (상세창까지 지워지는 것 방지)
    await page.evaluate('''() => {
        const popup = document.getElementById('mainPopup');
        if (popup) popup.style.display = 'none';
    }''')

    print("2. AP=[120120550993] 검색...")
    await page.fill("#inputQuery", "AP=[120120550993]")
    await page.click("button.btn-search", force=True)
    
    await page.wait_for_selector("button.link.under", timeout=15000)
    print("3. 검색 완료. 특허 순회를 시작합니다.\n")
    
    # KIPRIS는 페이지네이션이 있으나, 우선 첫 페이지에 보이는 모든 결과를 순회
    # (실제 대량 수집 시에는 '다음 페이지' 버튼 클릭 로직이 추가로 필요합니다)
    patent_links = await page.locator("button.link.under").all()
    total_patents = len(patent_links)
    
    for i in range(total_patents):
        print(f"\n=====================================")
        print(f"[{i+1}/{total_patents}] 번째 특허 처리 시작...")
        
        # DOM 상태가 변할 수 있으므로 매번 요소를 새로 찾습니다.
        link = page.locator("button.link.under").nth(i)
        
        # 특허 제목 수집 및 정제
        raw_title = await link.inner_text()
        clean_title = re.sub(r'[\\/:*?"<>|]', '', raw_title.strip()) 
        
        # 상세 팝업 열기
        await link.click()
        await page.wait_for_selector(".detail-tab-body")
        time.sleep(2) 
        
        # === 1. 특허 메타데이터 추출 (IPC, 출원번호) ===
        detail_text = await page.locator(".detail-tab-body").inner_text()
        
        # 정규식을 통한 IPC 추출 (예: B60C, A47B 등)
        ipc_match = re.search(r'IPC[^\w]*([A-Z0-9]+)', detail_text)
        ipc = ipc_match.group(1) if ipc_match else "IPC없음"
        
        # 출원번호 추출 (10-13자리 숫자)
        app_match = re.search(r'출원번호[^\d]*(\d{10,13})', detail_text)
        app_num = app_match.group(1) if app_match else f"알수없음_{i}"
        
        # [IPC] 출원번호_제목 포맷으로 폴더명 생성
        folder_name = f"[{ipc[:3]}] {app_num}_{clean_title}" if ipc != "IPC없음" else f"[{ipc}] {app_num}_{clean_title}"
        folder_path = os.path.join("kipris_downloads", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"  => 폴더: {folder_name}")
        
        # === 2. 공보(메인 PDF) 다운로드 ===
        try:
            # 보통 상세정보 탭이나 상단에 a.btn-download-pdf 가 있습니다.
            pdf_btn = page.locator("a.btn-download-pdf").first
            if await pdf_btn.is_visible():
                print("  => '01_공보(본문)' 다운로드 중...")
                async with page.expect_download(timeout=30000) as dl_info:
                    await pdf_btn.click(force=True)
                dl = await dl_info.value
                await dl.save_as(os.path.join(folder_path, "01_공보.pdf"))
                time.sleep(2) # KIPRIS 서버 부하 방지
            else:
                print("  => '공보(본문)' 버튼이 보이지 않습니다.")
        except Exception as e:
            print(f"  => [에러] 공보 다운로드 실패: {e}")
            
        # === 3. 통합행정정보 (의견제출서, 보정서) 스킵 로직 적용 ===
        print("  => '통합행정정보' 탭 검사 (의견/보정서 스크래핑)...")
        try:
            await page.locator("button.btn-tab", has_text="통합행정정보").click(force=True)
            await page.wait_for_selector(".detail-tab-body table", state="visible")
            time.sleep(2)
            
            rows = await page.locator(".detail-tab-body table tbody tr").all()
            for row in rows:
                row_text = await row.inner_text()
                
                # 날짜 추출 (YYYY.MM.DD)
                date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', row_text)
                date_str = f"_{date_match.group(1)}{date_match.group(2)}{date_match.group(3)}" if date_match else ""
                
                if "의견제출서" in row_text:
                    prefix = f"02_의견제출서{date_str}.pdf"
                elif "보정서" in row_text:
                    prefix = f"03_보정서{date_str}.pdf"
                else:
                    continue # 다른 서류는 무시하고 스킵(패스)합니다!
                    
                print(f"  => 문서 발견: [{prefix}] - 다운로드 진행")
                btn = row.locator("a.btn-blank").first
                if await btn.is_visible():
                    async with page.expect_download(timeout=30000) as dl_info:
                        await btn.click(force=True)
                    dl = await dl_info.value
                    await dl.save_as(os.path.join(folder_path, prefix))
                    time.sleep(3)
                    
        except Exception as e:
            print(f"  => [안내] 통합행정정보 스캔 중 문제 발생 (서류가 없을 수 있음): {e}")

        # === 4. 도면 추출 및 각주를 파일명으로 활용 ===
        print("  => '도면 전체보기' 라벨 기반 이미지 다운로드...")
        try:
            draw_btn = page.locator("button#btnToggleBPList") # KIPRIS의 도면 전체보기 버튼
            if await draw_btn.is_visible():
                await draw_btn.click(force=True)
                time.sleep(2) 
                
                # 보통 KIPRIS 도면 팝업 안의 요소들 (향후 정확한 class에 맞게 미세조정 필요 구역)
                drawing_items = await page.locator("div.thumb, li.thumb").all()
                for d_idx, item in enumerate(drawing_items):
                    # 이미지 설명(라벨) 텍스트 긁어오기
                    label_text = await item.inner_text()
                    # '[도면1]' -> '도면1' 형태로 특수기호 삭제
                    clean_label = re.sub(r'[\s\[\]\\/:*?"<>|]', '', label_text.strip())
                    
                    if not clean_label:
                        clean_label = f"도면_{d_idx+1}"
                        
                    file_name = f"04_{clean_label}.jpg"
                    
                    # 도면 다운로드 버튼 클릭
                    img_dl_btn = item.locator("a.btn-download").first
                    if await img_dl_btn.is_visible():
                        async with page.expect_download(timeout=10000) as dl_info:
                            await img_dl_btn.click(force=True)
                        dl = await dl_info.value
                        await dl.save_as(os.path.join(folder_path, file_name))
                        print(f"    - 저장 완료: {file_name}")
                        time.sleep(1.5)
            else:
                 print("  => 도면 전체보기 버튼이 없습니다 (도면 없음).")
        except Exception as e:
            print(f"  => [안내] 도면 다운로드 중 에러: {e}")
            
        # 다음 특허 처리를 위해 상세창 닫기
        print("  => 해당 특허 창 닫고 다음으로 이동합니다.")
        try:
             await page.locator("button.btn-close").first.click(force=True)
             time.sleep(1)
        except:
             pass

    print("\n수집 작업이 정상적으로 1페이지 종료되었습니다.")
    await context.close()
    await browser.close()

async def main():
    try:
        async with async_playwright() as playwright:
            await run(playwright)
    except Exception as e:
        print(f"에러가 발생했습니다: {e}")

if __name__ == "__main__":
    asyncio.run(main())
