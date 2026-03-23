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
    
    # [자체 애드가드 기능] 불필요한 KIPRIS 팝업 배너 이미지는 네트워크 단에서 다운로드 원천 차단!
    async def adblock_route(route):
        url = route.request.url.lower()
        # 팝업 배너, 공지 이미지, 분석 툴 등을 차단
        if "popup" in url and ("png" in url or "jpg" in url or "gif" in url):
            await route.abort()
        else:
            await route.continue_()
            
    await context.route("**/*", adblock_route)
    
    page = await context.new_page()

    # KIPRIS의 복잡한 팝업/다운로드 방식을 모두 커버하는 스마트 다운로드 함수
    async def smart_download(btn, save_path):
        try:
            # 1단계: KIPRIS는 보통 파일을 '새 탭'으로 열어버림 (브라우저 PDF 뷰어)
            async with context.expect_page(timeout=5000) as new_page_info:
                await btn.click(force=True)
            
            new_page = await new_page_info.value
            await new_page.wait_for_load_state() 
            
            pdf_url = new_page.url
            print(f"      - [새 창 감지] 해당 URL에서 직접 파일 다운로드를 시도합니다.")
            
            # 파이썬이 해당 URL의 파일의 원시 바이트를 직접 가져와서 PDF로 굽습니다 (가장 확실한 방법)
            response = await context.request.get(pdf_url)
            with open(save_path, "wb") as f:
                f.write(await response.body())
                
            await new_page.close() # 할 일 다 한 새 탭은 닫아줌
            print("      - [저장 완료]")
            return True
            
        except Exception:
            # 2단계: 새 탭이 안 열렸다면, KIPRIS가 진짜 백그라운드 "다운로드 폴더"로 던져준 것!
            try:
                # 일반적인 파일 다운로드 이벤트 수신 대기
                async with page.expect_download(timeout=10000) as dl_info:
                    await btn.click(force=True)
                dl = await dl_info.value
                await dl.save_as(save_path)
                print("      - [일반 다운로드 저장 완료]")
                return True
            except Exception as e2:
                print("      - [실패] 다운로드나 팝업 창을 잡아내지 못했습니다.")
                return False

    print("1. KIPRIS 사이트 접속 중...")
    await page.goto("https://www.kipris.or.kr/khome/main.do", wait_until="networkidle")

    # 메인 페이지 공지 팝업 제거 (직접 닫기 버튼 클릭)
    try:
        await page.locator("#mainPopup .btn-close").click(timeout=3000)
        time.sleep(1)
    except:
        pass
        
    # 혹시 남은 장애물 팝업이 있다면 강제 숨김 처리 (.remove() 사용 시 KIPRIS 전체 JS에러 발생 위험)
    await page.evaluate('''() => {
        const popup = document.getElementById('mainPopup');
        if (popup) popup.style.display = 'none';
    }''')

    print("2. AP=[120120550993] 검색...")
    await page.fill("#inputQuery", "AP=[120120550993]")
    await page.click("button.btn-search", force=True)
    
    await page.wait_for_selector("button.link.under", timeout=15000)
    
    # 회원님 지시사항: 검색 결과가 뜨자마자 빛의 속도로 누르면 KIPRIS 서버가 클릭을 무시하므로, 사람처럼 3초간 뜸을 들입니다.
    print("3. 검색 완료. 리스트 로딩을 위해 3초간 대기합니다...")
    time.sleep(3)
    
    # [최종 방어 로직] KIPRIS가 회원님의 기존 '목록보기(새창)' 설정을 기억하고 자꾸 새 브라우저 창을 띄우는 사태를 방지합니다.
    # 봇이 데이터를 가장 잘 뽑아올 수 있는 '분할보기(단일창 오버레이)' 버튼을 강제로 눌러서 모드를 고정합니다.
    try:
        split_btn = page.locator("a, button").filter(has_text="분할보기").first
        if await split_btn.is_visible(timeout=2000):
            await split_btn.click()
            time.sleep(2) # 뷰 모드 전환 대기
            print("  => 크롤러 전용 [분할보기] 모드로 강제 고정 완료!")
    except:
        pass
    
    print("  => 최상의 안정성을 위해 KIPRIS 기본 분할 모드에서 특허 다운로드를 진행합니다.\n")
    
    patent_links = await page.locator("button.link.under").all()
    total_patents = len(patent_links)
    
    for i in range(total_patents):
        print(f"\n=====================================")
        print(f"[{i+1}/{total_patents}] 번째 특허 처리 시작...")
        
        link = page.locator("button.link.under").nth(i)
        raw_title = await link.inner_text()
        clean_title = re.sub(r'[\\/:*?"<>|]', '', raw_title.strip()) 
        
        # 회원님의 '상세창 뜰 때까지 무한 클릭' 아이디어 적용!
        popup_opened = False
        for attempt in range(5):
            try:
                # 클릭 대상의 내부 JS 코드를 파이썬이 직접 실행시켜버립니다. (가장 확실한 클릭 판정)
                onclick_attr = await link.get_attribute("onclick")
                if onclick_attr and "getDetailPage" in onclick_attr:
                    await page.evaluate(onclick_attr)
                else:
                    await link.click(force=True)
                    
                await page.wait_for_selector(".detail-tab-body", timeout=15000)
                popup_opened = True
                break
            except Exception as e:
                print(f"      - [대기 초과 / 재시도] 에러 원인: {str(e)[:100]}...")
                time.sleep(1)
                
        if not popup_opened:
            print("      - [실패] 5번이나 클릭했는데도 열리지 않습니다. 이 특허는 패스합니다.")
            continue
        
        time.sleep(1) # 안정화 대기
        
        detail_text = await page.locator(".detail-tab-body").inner_text()
        
        ipc_match = re.search(r'IPC[^\w]*([A-Z0-9]+)', detail_text)
        ipc = ipc_match.group(1) if ipc_match else "IPC없음"
        
        app_match = re.search(r'출원번호[^\d]*(\d{10,13})', detail_text)
        app_num = app_match.group(1) if app_match else f"알수없음_{i}"
        
        folder_name = f"[{ipc[:3]}] {app_num}_{clean_title}" if ipc != "IPC없음" else f"[{ipc}] {app_num}_{clean_title}"
        folder_path = os.path.join("kipris_downloads", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"  => 폴더: {folder_name}")
        
        # === 2. 공보(메인 PDF) 다운로드 ===
        try:
            pdf_btn = page.locator("a.btn-download-pdf").first
            if await pdf_btn.is_visible():
                print("  => '01_공보(본문)' 다운로드 중 (URL 직접 추출)...")
                onclick_attr = await pdf_btn.get_attribute("onclick")
                
                # onclick="GoDownFullText({applno : '1020240124655', pub_reg : 'P'}); return false;"
                applno_m = re.search(r"applno\s*:\s*'([^']+)'", onclick_attr) if onclick_attr else None
                pub_reg_m = re.search(r"pub_reg\s*:\s*'([^']+)'", onclick_attr) if onclick_attr else None
                
                if applno_m and pub_reg_m:
                    pdf_url = f"https://www.kipris.or.kr/kpat/remoteFile.do?method=fullText&applno={applno_m.group(1)}&pub_reg={pub_reg_m.group(1)}"
                    # 브라우저 컨텍스트의 세션을 유지하며 직접 다운로드
                    response = await context.request.get(pdf_url)
                    if response.ok:
                        with open(os.path.join(folder_path, "01_공보.pdf"), "wb") as f:
                            f.write(await response.body())
                        print("  => '01_공보(본문)' 다운로드 완료!")
                    else:
                        print("  => '01_공보(본문)' 직접 다운로드 실패 (HTTP 에러)")
                else:
                    # 파라미터가 없으면 기존 스마트 다운로드 폴백
                    await smart_download(pdf_btn, os.path.join(folder_path, "01_공보.pdf"))
        except Exception as e:
            print(f"  => '01_공보(본문)' 처리 에러: {e}")
            
        # === 3. 통합행정정보 (의견제출서, 보정서) 스킵 로직 적용 ===
        print("  => '통합행정정보' 탭 검사 (의견/보정서 스크래핑)...")
        try:
            tab_opened = False
            for attempt in range(3):
                try:
                    await page.locator("button.btn-tab", has_text="통합행정정보").click(force=True)
                    await page.wait_for_selector(".detail-tab-body table", state="visible", timeout=5000)
                    tab_opened = True
                    break
                except:
                    time.sleep(1)
                    
            if not tab_opened:
                raise Exception("탭 클릭 3회 실패")
                
            time.sleep(1)
            
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
                    
                print(f"  => 문서 발견: [{prefix}] - 다운로드 진행")
                btn = row.locator("a.btn-blank").first
                if await btn.is_visible():
                    await smart_download(btn, os.path.join(folder_path, prefix))
                    time.sleep(3)
        except Exception as e:
            pass

        # === 4. 도면 추출 및 각주를 파일명으로 활용 ===
        print("  => '도면 전체보기' 라벨 기반 이미지 다운로드...")
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
                        time.sleep(1.5)
            else:
                 print("  => 도면 전체보기 버튼이 없습니다 (도면 없음).")
        except Exception as e:
            pass
            
        print("  => 해당 특허 창 닫고 다음으로 이동합니다.")
        try:
             await page.locator("button.btn-close").first.click(force=True)
             time.sleep(1)
        except:
             pass

    print("\n수집 작업이 정상적으로 종료되었습니다.")
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
