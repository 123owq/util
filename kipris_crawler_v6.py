import asyncio
from playwright.async_api import async_playwright
import time
import os
import re

async def run(playwright):
    browser = await playwright.chromium.launch(headless=False) # 디버깅을 위해 headless=False 권장 (사용자 환경)
    context = await browser.new_context(
        accept_downloads=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    )
    
    # 듀얼 탭 구조 유지
    search_page = await context.new_page()
    detail_page = await context.new_page() 

    async def smart_download(btn, save_path):
        try:
            async with context.expect_page(timeout=10000) as new_page_info:
                await btn.click(force=True)
            new_page = await new_page_info.value
            await new_page.wait_for_load_state()
            pdf_url = new_page.url
            response = await context.request.get(pdf_url)
            with open(save_path, "wb") as f:
                f.write(await response.body())
            await new_page.close()
            return True
        except:
            try:
                async with detail_page.expect_download(timeout=10000) as dl_info:
                    await btn.click(force=True)
                dl = await dl_info.value
                await dl.save_as(save_path)
                return True
            except:
                return False

    print("1. KIPRIS 접속 및 팝업 제거...")
    await search_page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="domcontentloaded")
    
    # 모든 팝업 요소를 즉시 숨김 (JS 주입)
    await search_page.add_style_tag(content="#mainPopup, .popup-dim, .divPopup, #divPopup { display: none !important; }")
    
    print("2. AP 검색어 입력 및 실행...")
    await search_page.fill("#inputQuery", "AP=[120120550993]")
    # 검색 버튼을 강제로 클릭 (팝업이 숨겨져 있어도 안정적으로 실행)
    await search_page.click("button.btn-search", force=True)
    
    print("3. 검색 결과 로딩 대기...")
    try:
        # 검색 결과가 나타나는 실제 리스트 컨테이너 대기
        await search_page.wait_for_selector(".search_result_list", timeout=20000)
        print("   - 결과 로딩 성공!")
    except:
        print("   - 결과 로딩 실패. 페이지 구조를 다시 확인해야 합니다.")
        await browser.close()
        return

    # 검색 결과에서 실제 특허 링크 추출
    all_links = await search_page.locator("button.link.under").all()
    real_patent_links = []
    for link in all_links:
        onclick_attr = await link.get_attribute("onclick")
        if onclick_attr and "openDetail" in onclick_attr:
            real_patent_links.append(link)
            
    total_patents = min(len(real_patent_links), 10)
    print(f"  => 실제 대상: {len(real_patent_links)}건 중 최대 {total_patents}건 진행\n")
    
    for i in range(total_patents):
        print(f"[{i+1}/{total_patents}] 처리 중...")
        link = real_patent_links[i]
        raw_title = await link.inner_text()
        clean_title = re.sub(r'[\\/:*?"<>|]', '', raw_title.strip()) 
        onclick_attr = await link.get_attribute("onclick")
        
        # 출원번호 추출 (정규식 고도화)
        applno_m = re.search(r"openDetail\('[^']+',\s*'(\d+)'", onclick_attr)
        if not applno_m: continue
        applno = applno_m.group(1)
        
        # 상세 페이지 접속
        detail_url = f"https://www.kipris.or.kr/kpat/detailView.do?applno={applno}"
        await detail_page.goto(detail_url, wait_until="domcontentloaded")
        
        try:
            await detail_page.wait_for_selector(".detail-tab-body", timeout=10000)
            detail_text = await detail_page.locator(".detail-tab-body").inner_text()
            
            # IPC 및 폴더 생성
            ipc_match = re.search(r'IPC[^\w]*([A-Z0-9]+)', detail_text)
            ipc = ipc_match.group(1) if ipc_match else "IPC없음"
            folder_name = f"[{ipc[:3]}] {applno}_{clean_title}"
            folder_path = os.path.join("kipris_downloads", folder_name)
            os.makedirs(folder_path, exist_ok=True)
            
            # 1. 공보 PDF (다이렉트 방식)
            pdf_url = f"https://www.kipris.or.kr/kpat/remoteFile.do?method=fullText&applno={applno}"
            res = await context.request.get(pdf_url)
            with open(os.path.join(folder_path, "01_공보.pdf"), "wb") as f:
                f.write(await res.body())
            print(f"      - [01_공보] 완료")

            # 2. 통합행정정보 (의견제출서, 보정서)
            try:
                await detail_page.click("button.btn-tab:has-text('통합행정정보')", force=True)
                await detail_page.wait_for_selector(".detail-tab-body table", timeout=5000)
                rows = await detail_page.locator(".detail-tab-body table tbody tr").all()
                for row in rows:
                    txt = await row.inner_text()
                    date_m = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', txt)
                    date_str = f"_{date_m.group(1)}{date_m.group(2)}{date_m.group(3)}" if date_m else ""
                    
                    prefix = ""
                    if "의견제출서" in txt: prefix = f"02_의견제출서{date_str}.pdf"
                    elif "보정서" in txt: prefix = f"03_보정서{date_str}.pdf"
                    
                    if prefix:
                        btn = row.locator("a.btn-blank").first
                        if await btn.is_visible():
                            await smart_download(btn, os.path.join(folder_path, prefix))
                print(f"      - [행정문서] 완료")
            except: pass

            # 3. 도면 다운로드
            try:
                draw_btn = detail_page.locator("button#btnToggleBPList")
                if await draw_btn.is_visible():
                    await draw_btn.click(force=True)
                    await asyncio.sleep(2)
                    thumbs = await detail_page.locator("div.thumb, li.thumb").all()
                    for idx, thumb in enumerate(thumbs):
                        img_btn = thumb.locator("a.btn-download").first
                        if await img_btn.is_visible():
                            await smart_download(img_btn, os.path.join(folder_path, f"04_도면_{idx+1}.jpg"))
                print(f"      - [도면] 완료")
            except: pass

        except Exception as e:
            print(f"   - 처리 중 오류: {e}")

    await context.close()
    await browser.close()

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
