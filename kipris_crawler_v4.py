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

    async def smart_download(btn, save_path):
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                await btn.click(force=True)
            new_page = await new_page_info.value
            await new_page.wait_for_load_state()
            pdf_url = new_page.url
            print(f"      - [새 창 감지] 직접 파일 다운로드 중...")
            response = await context.request.get(pdf_url)
            with open(save_path, "wb") as f:
                f.write(await response.body())
            await new_page.close()
            print("      - [저장 완료]")
            return True
        except Exception:
            try:
                async with page.expect_download(timeout=10000) as dl_info:
                    await btn.click(force=True)
                dl = await dl_info.value
                await dl.save_as(save_path)
                print("      - [일반 다운로드 완료]")
                return True
            except:
                print("      - [실패] 다운로드 창 감지 못함.")
                return False

    print("1. KIPRIS 접속 중...")
    await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="domcontentloaded")

    try:
        await page.locator("#mainPopup .btn-close, .popup-close").first.click(timeout=3000)
        time.sleep(1)
    except:
        pass

    await page.evaluate('''() => {
        const p = document.getElementById('mainPopup');
        if(p) p.style.display = 'none';
    }''')

    print("2. AP 검색...")
    await page.fill("#inputQuery", "AP=[120120550993]")
    await page.keyboard.press("Enter")
    
    try:
        await page.wait_for_selector("button.link.under", timeout=30000)
    except:
        print("검색 버튼으로 재시도...")
        await page.click("button.btn-search", force=True)
        await page.wait_for_selector("button.link.under", timeout=30000)
    print("3. 검색 완료. 화면 출력을 위해 3초 대기합니다...")
    time.sleep(3)
    
    patent_links = await page.locator("button.link.under").all()
    total_patents = len(patent_links)
    
    for i in range(total_patents):
        print(f"\n=====================================")
        print(f"[{i+1}/{total_patents}] 번째 특허 처리...")
        
        link = page.locator("button.link.under").nth(i)
        raw_title = await link.inner_text()
        clean_title = re.sub(r'[\\/:*?"<>|]', '', raw_title.strip()) 
        
        popup_opened = False
        for attempt in range(5):
            try:
                # 안전한 방식: 클릭 이벤트 오작동을 막기 위해 직접 자바스크립트 호출
                onclick_attr = await link.get_attribute("onclick")
                if onclick_attr and "getDetailPage" in onclick_attr:
                    await page.evaluate(onclick_attr)
                else:
                    await link.click(force=True)
                    
                await page.wait_for_selector(".detail-tab-body", timeout=15000)
                popup_opened = True
                break
            except Exception as e:
                print(f"      - [상세창 대기 시간 초과] 다시 시도합니다...")
                time.sleep(1)
                
        if not popup_opened:
            print("      - [실패] 5번 팝업 시도 후 실패. 스킵합니다.")
            continue
        
        time.sleep(1)
        detail_text = await page.locator(".detail-tab-body").inner_text()
        
        ipc_match = re.search(r'IPC[^\w]*([A-Z0-9]+)', detail_text)
        ipc = ipc_match.group(1) if ipc_match else "IPC없음"
        app_match = re.search(r'출원번호[^\d]*(\d{10,13})', detail_text)
        app_num = app_match.group(1) if app_match else f"알수없음_{i}"
        
        folder_name = f"[{ipc[:3]}] {app_num}_{clean_title}" if ipc != "IPC없음" else f"[{ipc}] {app_num}_{clean_title}"
        folder_path = os.path.join("kipris_downloads", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"  => 폴더: {folder_name}")
        
        # === 2. 메인 공보 다운로드 (URL 직접 추출 방식) ===
        try:
            pdf_btn = page.locator("a.btn-download-pdf").first
            if await pdf_btn.is_visible():
                onclick_attr = await pdf_btn.get_attribute("onclick")
                applno_m = re.search(r"applno\s*:\s*'([^']+)'", onclick_attr) if onclick_attr else None
                pub_reg_m = re.search(r"pub_reg\s*:\s*'([^']+)'", onclick_attr) if onclick_attr else None
                
                if applno_m and pub_reg_m:
                    pdf_url = f"https://www.kipris.or.kr/kpat/remoteFile.do?method=fullText&applno={applno_m.group(1)}&pub_reg={pub_reg_m.group(1)}"
                    response = await context.request.get(pdf_url)
                    with open(os.path.join(folder_path, "01_공보.pdf"), "wb") as f:
                        f.write(await response.body())
                    print("  => [01_공보] 다운로드 완료!")
                else:
                    await smart_download(pdf_btn, os.path.join(folder_path, "01_공보.pdf"))
        except:
            pass
            
        print("  => 통합행정정보 분석...")
        try:
            tab_opened = False
            for attempt in range(3):
                try:
                    await page.locator("button.btn-tab", has_text="통합행정정보").click(force=True)
                    await page.wait_for_selector(".detail-tab-body table", state="visible", timeout=10000)
                    tab_opened = True
                    break
                except:
                    time.sleep(1)
            time.sleep(1)
            
            if tab_opened:
                rows = await page.locator(".detail-tab-body table tbody tr").all()
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
            draw_btn = page.locator("button#btnToggleBPList") 
            if await draw_btn.is_visible():
                await draw_btn.click(force=True)
                time.sleep(2) 
                
                drawing_items = await page.locator("div.thumb, li.thumb").all()
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
            
        print("  => 다음 특허로 이동\n")
        try:
             await page.locator(".popup-close, button.btn-close").first.click(force=True)
             time.sleep(1)
        except:
             pass

    await context.close()
    await browser.close()

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())
