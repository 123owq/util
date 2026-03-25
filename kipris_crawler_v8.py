"""
KIPRIS 정밀 수집 시스템 v9
- 엑셀 등록번호 목록 기반 수집
- 등록번호 → 검색 → applno 추출 → 상세 다운로드
"""

import asyncio
import os
import re
import random
import logging
import traceback
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
EXCEL_FILE   = os.environ.get("EXCEL_FILE", "20260323133300.xlsx")
MAX_COUNT    = int(os.environ.get("MAX_COUNT", 10))
OUTPUT_DIR   = os.environ.get("OUTPUT_DIR", "kipris_downloads")
HEADLESS     = os.environ.get("HEADLESS", "false").lower() == "true"

# 로거 세팅
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"kipris_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8")
    ]
)
log = logging.getLogger("KIPRIS")


# ─────────────────────────────────────────────
# 엑셀에서 등록번호 로드
# ─────────────────────────────────────────────
def load_reg_numbers(path: str) -> list[str]:
    df = pd.read_excel(path, header=7, engine='calamine')
    df.columns = ['순번', '발명명칭', '등록번호', '등록일자']
    df = df.dropna(subset=['등록번호'])
    nums = df['등록번호'].astype(str).str.strip().tolist()
    log.info(f"엑셀 로드 완료: {len(nums)}건 ({path})")
    return nums


# ─────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────

def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name[:max_len]


async def human_delay(min_s=0.8, max_s=2.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_type(page, selector: str, text: str):
    await page.click(selector)
    await human_delay(0.3, 0.7)
    await page.fill(selector, "")
    await human_delay(0.2, 0.5)
    for char in text:
        await page.type(selector, char, delay=random.randint(60, 180))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.3, 0.8))


async def bezier_mouse_move(page, x1, y1, x2, y2, steps=25):
    cp1x = x1 + (x2 - x1) * 0.3 + random.randint(-80, 80)
    cp1y = y1 + (y2 - y1) * 0.3 + random.randint(-80, 80)
    cp2x = x1 + (x2 - x1) * 0.7 + random.randint(-80, 80)
    cp2y = y1 + (y2 - y1) * 0.7 + random.randint(-80, 80)
    for i in range(steps + 1):
        t = i / steps
        bx = ((1-t)**3 * x1 + 3*(1-t)**2*t * cp1x
              + 3*(1-t)*t**2 * cp2x + t**3 * x2)
        by = ((1-t)**3 * y1 + 3*(1-t)**2*t * cp1y
              + 3*(1-t)*t**2 * cp2y + t**3 * y2)
        await page.mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.005, 0.02))


async def human_click(page, selector: str):
    element = page.locator(selector).first
    bbox = await element.bounding_box()
    if not bbox:
        await element.click(force=True)
        return
    tx = bbox['x'] + bbox['width']  * random.uniform(0.3, 0.7)
    ty = bbox['y'] + bbox['height'] * random.uniform(0.3, 0.7)
    sx = random.randint(100, 1800)
    sy = random.randint(100, 900)
    await bezier_mouse_move(page, sx, sy, tx, ty)
    await human_delay(0.1, 0.3)
    await page.mouse.click(tx, ty)


async def human_scroll(page, direction="down", times=3):
    for _ in range(times):
        delta = random.randint(200, 500) * (1 if direction == "down" else -1)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.3, 0.8))


async def retry_goto(page, url: str, retries=3, wait_until="domcontentloaded"):
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until=wait_until, timeout=30000)
            return True
        except Exception as e:
            log.warning(f"[재시도 {attempt+1}/{retries}] {url} → {e}")
            await asyncio.sleep(random.uniform(3, 7))
    return False


async def wait_for_any(page, selectors: list, timeout=15000):
    async def _try(sel):
        try:
            await page.wait_for_selector(sel, timeout=timeout)
            return True
        except Exception:
            return False

    tasks = [asyncio.ensure_future(_try(sel)) for sel in selectors]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for p in pending:
        p.cancel()
    # 취소된 태스크 결과 수집 (CancelledError 무시)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return any(t.result() is True for t in done if not t.cancelled() and t.exception() is None)


# ─────────────────────────────────────────────
# 스텔스 스크립트
# ─────────────────────────────────────────────
STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
        ]
    });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
}
"""


# ─────────────────────────────────────────────
# 다운로더
# ─────────────────────────────────────────────
async def download_direct(context, url: str, save_path: str, retries=2) -> bool:
    for attempt in range(retries):
        try:
            response = await context.request.get(url, timeout=20000)
            if response.status == 200:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(await response.body())
                return True
            log.warning(f"다운로드 실패 (HTTP {response.status}): {url}")
        except Exception as e:
            log.warning(f"다운로드 오류 [{attempt+1}/{retries}]: {e}")
            await asyncio.sleep(2)
    return False


# ─────────────────────────────────────────────
# 팝업 제거
# ─────────────────────────────────────────────
async def kill_popups(page):
    await page.evaluate("""() => {
        const sels = [
            '#mainPopup', '.popup-dim', '.divPopup', '#divPopup',
            '.ui-widget-overlay', '.ui-dialog', '.layer-popup',
            '[class*="popup"]', '[id*="popup"]', '[class*="modal"]'
        ];
        sels.forEach(s => {
            try { document.querySelectorAll(s).forEach(el => el.remove()); } catch(e){}
        });
        document.body.style.overflow = 'auto';
    }""")


# ─────────────────────────────────────────────
# IPC 추출
# ─────────────────────────────────────────────
async def extract_ipc(page) -> str:
    candidates = [
        ".ipc-code", ".ipcCode", "[class*='ipc']",
        "td:has-text('IPC') + td", "th:has-text('IPC') ~ td"
    ]
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                text = (await el.inner_text()).strip()
                if text:
                    return re.sub(r'\s+', '', text)[:6]
        except Exception:
            pass
    try:
        html = await page.content()
        m = re.search(r'\b([A-H]\d{2}[A-Z]\s*\d+/\d+)\b', html)
        if m:
            return re.sub(r'\s+', '', m.group(1))[:6]
    except Exception:
        pass
    return "IPC없음"


# ─────────────────────────────────────────────
# 검색 → 버튼 클릭 → 상세 페이지 반환
# ─────────────────────────────────────────────
async def search_and_open_detail(page, context, reg_no: str):
    """
    등록번호로 검색 후 결과 클릭.
    (detail_page, applno, title) 반환. 실패 시 None.
    새 탭이 열리면 그 탭을, 같은 페이지면 page 그대로 반환.
    """
    await human_type(page, "#inputQuery", f"RN=[{reg_no}]")
    await human_delay(0.5, 1.2)
    await human_click(page, "button.btn-search")

    # 결과 대기
    found = await wait_for_any(
        page,
        [".search_result_list", ".result-list", "#searchResultList", "button.link.under"],
        timeout=25000
    )
    if not found:
        await page.screenshot(path=f"debug_fail_{reg_no}.png")
        log.warning(f"  결과 없음: {reg_no} → 스크린샷 저장")
        return None

    await human_delay(1.0, 2.0)
    await kill_popups(page)

    # 클릭할 버튼 찾기
    btn_elem = None
    applno   = None
    title    = reg_no

    selectors = [
        "button.link.under",
        "button[onclick*='openDetail']",
        "a[onclick*='openDetail']",
        "[onclick*='openDetail']",
    ]
    for sel in selectors:
        try:
            elems = await page.locator(sel).all()
            for elem in elems:
                oc = await elem.get_attribute("onclick") or ""
                if "openDetail" not in oc:
                    continue
                m = re.search(r"openDetail\('[^']*',\s*'(\d+)'", oc)
                if not m:
                    m = re.search(r"openDetail\('(\d+)'", oc)
                if not m:
                    continue
                applno   = m.group(1)
                title    = safe_filename((await elem.inner_text()).strip()) or reg_no
                btn_elem = elem
                log.info(f"  버튼 발견 [{sel}] applno={applno}")
                break
        except Exception:
            continue
        if btn_elem:
            break

    # HTML 파싱 fallback (버튼은 못 찾았지만 applno는 있는 경우)
    if not applno:
        try:
            html = await page.content()
            m = re.search(r"openDetail\('[^']*',\s*'(\d+)'", html)
            if not m:
                m = re.search(r"openDetail\('(\d+)'", html)
            if m:
                applno = m.group(1)
                log.info(f"  HTML에서 applno 추출: {applno}")
        except Exception:
            pass

    if not applno:
        await page.screenshot(path=f"debug_noresult_{reg_no}.png")
        log.warning(f"  applno 추출 실패: {reg_no}")
        return None

    # 버튼 클릭 → 새 탭 or 같은 페이지 전환 감지
    if btn_elem:
        try:
            async with context.expect_page(timeout=8000) as new_page_info:
                await btn_elem.click()
            detail_page = await new_page_info.value
            await detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
            log.info("  새 탭으로 상세 페이지 열림")
            return detail_page, applno, title
        except Exception:
            # 새 탭 없이 같은 페이지에서 전환된 경우
            log.info("  같은 페이지에서 상세 전환")
            await human_delay(1.5, 3.0)
            return page, applno, title
    else:
        return page, applno, title


# ─────────────────────────────────────────────
# 상세 페이지 처리 (다운로드)
# ─────────────────────────────────────────────
async def process_detail(context, detail_page, applno: str, title: str, folder_path: str):
    await wait_for_any(
        detail_page,
        [".detail-tab-body", ".patent-detail", "#patentDetail", ".view-wrap"],
        timeout=15000
    )
    await kill_popups(detail_page)
    await human_scroll(detail_page, "down", times=3)
    await human_delay(1.5, 3.0)
    await human_scroll(detail_page, "up", times=1)
    await human_delay(0.5, 1.5)

    ipc = await extract_ipc(detail_page)
    log.info(f"  IPC: {ipc}")

    folder_path = os.path.join(folder_path, f"[{ipc[:3]}] {applno}_{title}")
    os.makedirs(folder_path, exist_ok=True)

    # ── (1) 공보 PDF ──────────────────────────
    log.info("  [다운로드] 공보 PDF...")
    pdf_url = f"https://www.kipris.or.kr/kpat/remoteFile.do?method=fullText&applno={applno}"
    result = await download_direct(context, pdf_url, os.path.join(folder_path, "01_공보.pdf"))
    log.info(f"    → {'성공' if result else '실패'}")

    await human_delay(1.0, 2.5)

    # ── (2) 통합행정정보 ──────────────────────
    log.info("  [탭] 통합행정정보 클릭...")
    try:
        tab_btn = detail_page.locator("button.btn-tab:has-text('통합행정정보')").first
        if await tab_btn.is_visible(timeout=5000):
            await human_click(detail_page, "button.btn-tab:has-text('통합행정정보')")
            # AJAX 로딩 충분히 대기
            await human_delay(2.5, 4.0)
            try:
                await detail_page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await human_delay(1.0, 2.0)

            rows = await detail_page.locator(".detail-tab-body table tbody tr").all()
            for row in rows:
                try:
                    txt = await row.inner_text()
                    date_m  = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', txt)
                    date_str = f"_{date_m.group(1)}{date_m.group(2)}{date_m.group(3)}" if date_m else ""

                    prefix = ""
                    if "의견제출서" in txt:
                        prefix = f"02_의견제출서{date_str}.pdf"
                    elif "보정서" in txt:
                        prefix = f"03_보정서{date_str}.pdf"
                    if not prefix:
                        continue

                    doc_btn = row.locator("a[onclick*='openDocument']").first
                    if not await doc_btn.is_visible():
                        continue

                    oc      = await doc_btn.get_attribute("onclick") or ""
                    path_m  = re.search(
                        r"openDocument\s*\([^,]+,[^,]+,[^,]+,\s*'([^']+)'\s*\)", oc
                    )
                    if path_m and path_m.group(1):
                        dl_url = f"https://www.kipris.or.kr{path_m.group(1)}"
                        ok = await download_direct(context, dl_url, os.path.join(folder_path, prefix))
                        log.info(f"    → {prefix}: {'성공' if ok else '실패'}")
                    else:
                        try:
                            async with detail_page.expect_download(timeout=12000) as dl_info:
                                await doc_btn.click(force=True)
                            dl = await dl_info.value
                            await dl.save_as(os.path.join(folder_path, prefix))
                            log.info(f"    → {prefix}: 성공(팝업다운로드)")
                        except Exception as e:
                            log.warning(f"    → {prefix}: 실패 ({e})")

                    await human_delay(0.5, 1.5)

                except Exception as e:
                    log.warning(f"  행 처리 오류: {e}")

    except PWTimeout:
        log.warning("  통합행정정보 탭 타임아웃")
    except Exception as e:
        log.warning(f"  통합행정정보 처리 오류: {e}")

    await human_delay(1.0, 2.5)

    # ── (3) 도면 이미지 ───────────────────────
    log.info("  [도면] 전체보기 클릭...")
    try:
        draw_selectors = [
            "button#btnToggleBPList",
            "button[id*='toggleBP']",
            "button[id*='Toggle']",
            "a[onclick*='toggleBPList']",
            "button:has-text('전체보기')",
            "button:has-text('도면')",
        ]
        draw_btn = None
        for dsel in draw_selectors:
            try:
                el = detail_page.locator(dsel).first
                if await el.is_visible(timeout=2000):
                    draw_btn = dsel
                    break
            except Exception:
                continue

        if draw_btn:
            await human_click(detail_page, draw_btn)
            await human_delay(1.5, 3.0)
            try:
                await detail_page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await human_scroll(detail_page, "down", times=4)
            await human_delay(1.0, 2.0)
        else:
            # 버튼 없어도 HTML에서 도면 파일명 추출 시도
            log.info("    도면 버튼 없음, HTML에서 직접 추출 시도")
            await human_scroll(detail_page, "down", times=3)
            await human_delay(1.0, 2.0)

        curr_html  = await detail_page.content()
        file_names = sorted(set(
            re.findall(r'fileNm=(pat\d+\.(?:tif|jpg|png|gif))', curr_html)
        ))
        log.info(f"    도면 {len(file_names)}개 발견")

        for f_name in file_names:
            img_url   = (
                f"https://www.kipris.or.kr/kpat/remoteFile.do"
                f"?method=downloadImage&applno={applno}"
                f"&fileNm={f_name}&frontYn=N&downYn=Y"
            )
            save_name = f"04_도면_{f_name.replace('pat', '')}"
            ok = await download_direct(context, img_url, os.path.join(folder_path, save_name))
            if ok:
                log.info(f"    → {save_name}: 성공")
            await asyncio.sleep(random.uniform(0.3, 0.8))

    except PWTimeout:
        log.warning("  도면 로딩 타임아웃")
    except Exception as e:
        log.warning(f"  도면 처리 오류: {e}")

    return True


# ─────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────
async def run(playwright):
    # ── 엑셀 로드 ─────────────────────────────
    reg_numbers = load_reg_numbers(EXCEL_FILE)
    total = min(len(reg_numbers), MAX_COUNT)

    log.info("=" * 60)
    log.info("[v9] KIPRIS 등록번호 기반 수집 시스템 가동")
    log.info(f"  엑셀: {EXCEL_FILE} | 총 {len(reg_numbers)}건 | 처리 예정: {total}건")
    log.info("=" * 60)

    # ── 브라우저 설정 ──────────────────────────
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1280,800",
        ]
    )

    context = await browser.new_context(
        accept_downloads=True,
        viewport={'width': 1280, 'height': 800},
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        ),
        locale='ko-KR',
        timezone_id='Asia/Seoul',
        extra_http_headers={
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }
    )
    await context.add_init_script(STEALTH_JS)

    # ── 등록번호별 루프 (특허마다 새 페이지) ──
    success_count = 0
    fail_list     = []

    for i, reg_no in enumerate(reg_numbers[:total]):
        log.info(f"{'='*50}")
        log.info(f"[{i+1}/{total}] 등록번호: {reg_no}")

        page = await context.new_page()
        detail_page = None
        try:
            # 메인 접속
            ok = await retry_goto(page, "https://www.kipris.or.kr/khome/main.do")
            if not ok:
                log.error(f"  접속 실패: {reg_no}")
                fail_list.append(reg_no)
                continue

            await human_delay(1.5, 3.0)
            await kill_popups(page)

            # 검색 → 버튼 클릭 → 상세 페이지
            result = await search_and_open_detail(page, context, reg_no)
            if result is None:
                fail_list.append(reg_no)
                continue
            detail_page, applno, title = result
            log.info(f"  출원번호: {applno} | 제목: {title[:40]}")

            # 상세 다운로드
            ok = await process_detail(context, detail_page, applno, title, OUTPUT_DIR)
            if ok:
                success_count += 1
                log.info(f"  [{reg_no}] 완료\n")
            else:
                fail_list.append(reg_no)

        except Exception as e:
            log.error(f"  예외 발생: {e}")
            fail_list.append(reg_no)
        finally:
            # 새 탭이 열렸으면 닫기
            if detail_page and detail_page is not page:
                try:
                    await detail_page.close()
                except Exception:
                    pass
            try:
                await page.close()
            except Exception:
                pass

        # 다음 특허 전 딜레이
        if i < total - 1:
            wait_sec = random.uniform(3.0, 7.0)
            log.info(f"  다음 특허 전 대기: {wait_sec:.1f}초...")
            await asyncio.sleep(wait_sec)

    # ── 결과 요약 ──────────────────────────────
    log.info("=" * 60)
    log.info(f"[완료] 성공: {success_count}/{total}건")
    if fail_list:
        log.warning(f"[실패 목록] {fail_list}")
    log.info(f"결과 폴더: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)

    await browser.close()


async def main():
    async with async_playwright() as p:
        await run(p)


if __name__ == "__main__":
    asyncio.run(main())
