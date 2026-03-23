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
    
    # [듀얼 탭 아키텍처] 검색 결과 리스트용 메인 탭과 상세 정보 파싱용 서브 탭을 분리하여 레이아웃 충돌 무력화
    search_page = await context.new_page()
    detail_page = await context.new_page() 

    async def smart_download(btn, save_path):
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                await btn.click(force=True)
            new_page = await new_page_info.value
            await new_page.wait_for_load_state()
            pdf_url = new_page.url
            response = await context.request.get(pdf_url)
            with open(save_path, "wb") as f:
                f.write(await response.body())
            await new_page.close()
            print("      - [저장 완료]")
            return True
        except Exception:
            try:
                async with detail_page.expect_download(timeout=10000) as dl_info:
                    await btn.click(force=True)
                dl = await dl_info.value
                await dl.save_as(save_path)
                print("      - [일반 다운로드 완료]")
                return True
            except:
                print("      - [실패] 다운로드 창 감지 못함.")
                return False

    print("1. KIPRIS 홈 접속...")
    await search_page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="domcontentloaded")
    
    try:
        await search_page.locator("#mainPopup .btn-close").click(timeout=2000)
        time.sleep(0.5)
    except:
        pass

    print("2. AP 검색...")
    await search_page.fill("#inputQuery", "AP=[120120550993]")
    await search_page.click("button.btn-search", force=True)
    
    # 검색 후 결과 목록이 완전히 나타날 때까지 충분히 기다림
    time.sleep(5)
    print("3. 검색 완료!")
    
    # 환경 조사로 확인: KIPRIS 검색 결과는 section.search_result_list > article 로 구성되지만,
    # Playwright에서는 일반 button.link.under 선택자가 더 안정적. onclick='applno' 필터링으로 진짜만 추리.
    all_links = await search_page.locator("button.link.under").all()
    real_patent_links = []
    
    # [KEY FIX] KIPRIS onclick 실제 형식: openDetail('kpat', '1020240124655', '', this)
    # applno가 아니라 openDetail 함수로 필터해야 함
    for link in all_links:
        onclick_attr = await link.get_attribute("onclick")
        if onclick_attr and "openDetail" in onclick_attr:
            real_patent_links.append(link)
            
    total_patents = min(len(real_patent_links), 10) # 회원님 요청사항: 10건만 제한
    print(f"  => 실제 다운로드 대상 특허: {len(real_patent_links)}건 중 최대 {total_patents}건만 진행합니다!\n")
    
    for i in range(total_patents):
        print(f"=====================================")
        print(f"[{i+1}/{total_patents}] 번째 진짜 특허 다운로드 시작...")
        
        link = real_patent_links[i]
        raw_title = await link.inner_text()
        clean_title = re.sub(r'[\\/:*?"<>|]', '', raw_title.strip()) 
        
        # 목록 화면의 버튼을 클릭해서 오버레이를 여는 불안정한 방식을 완전히 폐기.
        # HTML 태그 안에 숨겨진 출원번호(applno)를 정규식으로 직접 뽑아냅니다.
        onclick_attr = await link.get_attribute("onclick")
        if not onclick_attr:
            print("  => onclick 속성을 찾을 수 없어 스킵합니다.")
            continue
            
        # onclick 형식: openDetail('kpat', '1020240124655', '', this)
        # 두 번째 파라미터가 바로 출원번호
        applno_m = re.search(r"openDetail\('[^']+',\s*'([^']+)'", onclick_attr)
        pub_reg = 'P'  # 기본값
        
        if not applno_m:
            print("  => 출원번호를 찾을 수 없어 스킵합니다.")
            continue
            
        applno = applno_m.group(1)
        
        # [우회 타격] 두 번째 빈 탭(detail_page)에 특허 상세 정보 다이렉트 주소를 꽂아넣어서 바로 접속
        detail_url = f"https://www.kipris.or.kr/kpat/detailView.do?applno={applno}&pub_reg={pub_reg}"
        print(f"  => 독립 상세 탭으로 바로 접속 중... (레이아웃 붕괴 완벽 차단)")
        await detail_page.goto(detail_url, wait_until="domcontentloaded")
        try:
             await detail_page.wait_for_selector(".detail-tab-body", timeout=15000)
        except:
             print("  => 상세 페이지 로딩 대기 초과. 스킵합니다.")
             continue
        
        time.sleep(1)
        detail_text = await detail_page.locator(".detail-tab-body").inner_text()
        
        ipc_match = re.search(r'IPC[^\w]*([A-Z0-9]+)', detail_text)
        ipc = ipc_match.group(1) if ipc_match else "IPC없음"
        
        folder_name = f"[{ipc[:3]}] {applno}_{clean_title}" if ipc != "IPC없음" else f"[{ipc}] {applno}_{clean_title}"
        folder_path = os.path.join("kipris_downloads", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"  => 폴더: {folder_name}")
        
        # === 2. 메인 공보 다운로드 (URL 직접 추출 방식) ===
        try:
            pdf_url_direct = f"https://www.kipris.or.kr/kpat/remoteFile.do?method=fullText&applno={applno}&pub_reg={pub_reg}"
            response = await context.request.get(pdf_url_direct)
            with open(os.path.join(folder_path, "01_공보.pdf"), "wb") as f:
                f.write(await response.body())
            print("  => [01_공보] 다운로드 완료!")
        except Exception as e:
            print(f"  => [01_공보] 직접 다운로드 실패: {e}")
            
        print("  => 통합행정정보 분석...")
        try:
            tab_opened = False
            for attempt in range(3):
                try:
                    await detail_page.locator("button.btn-tab", has_text="통합행정정보").click(force=True)
                    await detail_page.wait_for_selector(".detail-tab-body table", state="visible", timeout=10000)
                    tab_opened = True
                    break
                except:
                    time.sleep(1)
            time.sleep(1)
            
            if tab_opened:
                rows = await detail_page.locator(".detail-tab-body table tbody tr").all()
                for row in rows:
                    row_text = await row.inner_text()
                    date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', row_text)
                    date_str = f"_{date_match.group(1)}{date_match.group(2)}{date_match.group(3)}" if date_match else ""
                    
                    if "의견제출서" in row_text:
                        prefix = f"02_의견제출서{date_str}.pdf"
                    elif "보정서" in row_text:
                        prefix = f"03_보정서{date_str}.pdf"
                    else:
                        continue 
                        
                    btn = row.locator("a.btn-blank").first
                    if await btn.is_visible():
                        print(f"  => [{prefix}] 다운로드...")
                        await smart_download(btn, os.path.join(folder_path, prefix))
        except:
            pass

        print("  => 도면 다운로드...")
        try:
            draw_btn = detail_page.locator("button#btnToggleBPList") 
            if await draw_btn.is_visible():
                await draw_btn.click(force=True)
                time.sleep(2) 
                
                drawing_items = await detail_page.locator("div.thumb, li.thumb").all()
                for d_idx, item in enumerate(drawing_items):
                    label_text = await item.inner_text()
                    clean_label = re.sub(r'[\s\[\]\\/:*?"<>|]', '', label_text.strip())
                    if not clean_label:
                        clean_label = f"도면_{d_idx+1}"
                    file_name = f"04_{clean_label}.jpg"
                    
                    img_dl_btn = item.locator("a.btn-download").first
                    if await img_dl_btn.is_visible():
                        await smart_download(img_dl_btn, os.path.join(folder_path, file_name))
        except:
            pass

    await context.close()
    await browser.close()

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
