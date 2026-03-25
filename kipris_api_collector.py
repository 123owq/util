"""
KIPRIS Plus API 수집기
- 엑셀에서 등록번호 로드
- 등록번호 → 출원번호 변환 (getAdvancedSearch)
- 출원번호 기반으로 수집:
    1. 특허 기본정보
    2. 의견제출통지서
    3. 선행특허 (인용문헌)
    4. 청구항변동이력
    5. 공개전문 PDF 정보
"""

import os
import re
import time
import json
import logging
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────
API_KEY    = "Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU="
EXCEL_FILE = "20260323133300.xlsx"
OUTPUT_DIR = "kipris_api_output"
MAX_COUNT  = int(os.environ.get("MAX_COUNT", 9999))
DELAY_SEC  = 0.5  # API 호출 간격 (초)

BASE = "http://plus.kipris.or.kr"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"kipris_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        )
    ]
)
log = logging.getLogger("KIPRIS_API")


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def safe_dirname(s: str, max_len=60) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s).strip()[:max_len]


def save_json(data, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def xml_to_dict(element: ET.Element) -> dict:
    """XML Element → dict (중복 태그는 리스트로)"""
    result = {}
    for child in element:
        tag = child.tag.split("}")[-1]  # namespace 제거
        value = xml_to_dict(child) if len(child) else (child.text or "")
        if tag in result:
            if not isinstance(result[tag], list):
                result[tag] = [result[tag]]
            result[tag].append(value)
        else:
            result[tag] = value
    return result


def find_all(root: ET.Element, tag: str) -> list[ET.Element]:
    """namespace 무관하게 tag 검색"""
    return root.findall(f".//{tag}") or root.findall(f".//*[local-name()='{tag}']")


# ─────────────────────────────────────────
# API 호출 공통
# ─────────────────────────────────────────
def api_get(url: str, params: dict, retries=3) -> ET.Element | None:
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except Exception as e:
            log.warning(f"  [재시도 {attempt+1}/{retries}] {e}")
            time.sleep(2)
    log.error(f"  API 호출 최종 실패: {url}")
    return None


# ─────────────────────────────────────────
# 엑셀 로드
# ─────────────────────────────────────────
def load_reg_numbers(path: str) -> list[dict]:
    df = pd.read_excel(path, header=7, engine="calamine", dtype=str)
    df.columns = ["순번", "발명명칭", "등록번호", "등록일자"]
    df = df.dropna(subset=["등록번호"])
    records = df[["발명명칭", "등록번호"]].to_dict("records")
    log.info(f"엑셀 로드: {len(records)}건 ({path})")
    return records


# ─────────────────────────────────────────
# 등록번호 → 출원번호
# ─────────────────────────────────────────
def get_application_number(reg_no: str) -> tuple[str, str] | None:
    root = api_get(
        f"{BASE}/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch",
        {"registerNumber": reg_no, "ServiceKey": API_KEY, "numOfRows": "1"}
    )
    if root is None:
        return None

    items = find_all(root, "item")
    if not items:
        log.warning(f"  등록번호 {reg_no}: 검색 결과 없음")
        return None

    item = items[0]
    appl_no = (item.findtext("applicationNumber") or "").strip()
    title   = (item.findtext("inventionTitle") or reg_no).strip()
    return (appl_no, title) if appl_no else None


# ─────────────────────────────────────────
# 수집 함수들
# ─────────────────────────────────────────
def fetch_basic_info(appl_no: str, folder: str):
    """특허 기본정보"""
    root = api_get(
        f"{BASE}/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch",
        {"applicationNumber": appl_no, "ServiceKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "item")
    if not items:
        log.info("    기본정보: 결과 없음")
        return

    save_json(xml_to_dict(items[0]), os.path.join(folder, "01_기본정보.json"))
    log.info("    01_기본정보.json 저장")


def fetch_office_actions(appl_no: str, folder: str):
    """의견제출통지서"""
    root = api_get(
        f"{BASE}/openapi/rest/IntermediateDocumentOPService/advancedSearchInfo",
        {
            "applicationNumber": appl_no,
            "patent": "true",
            "utility": "true",
            "accessKey": API_KEY,
        }
    )
    if root is None:
        return

    items = find_all(root, "item")
    if not items:
        log.info("    의견제출통지서: 없음")
        return

    data = [xml_to_dict(it) for it in items]
    save_json(data, os.path.join(folder, "02_의견제출통지서.json"))
    log.info(f"    02_의견제출통지서.json 저장 ({len(items)}건)")


def fetch_citations(appl_no: str, folder: str):
    """선행특허 (인용문헌)"""
    root = api_get(
        f"{BASE}/openapi/rest/CitationService/citationInfoV3",
        {"applicationNumber": appl_no, "accessKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "item")
    if not items:
        log.info("    선행특허: 없음")
        return

    data = [xml_to_dict(it) for it in items]
    save_json(data, os.path.join(folder, "03_선행특허.json"))
    log.info(f"    03_선행특허.json 저장 ({len(items)}건)")


def fetch_claims_history(appl_no: str, folder: str):
    """청구항 변동이력"""
    root = api_get(
        f"{BASE}/openapi/rest/ClaimsChangeHistoryService/amendmentHistoryInfo",
        {"applicationNumber": appl_no, "accessKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "item")
    if not items:
        log.info("    청구항변동이력: 없음")
        return

    data = [xml_to_dict(it) for it in items]
    save_json(data, os.path.join(folder, "04_청구항변동이력.json"))
    log.info(f"    04_청구항변동이력.json 저장 ({len(items)}건)")


def fetch_pub_pdf_info(appl_no: str, folder: str):
    """공개전문 PDF 정보 (+ PDF 파일이 URL로 제공되면 다운로드)"""
    root = api_get(
        f"{BASE}/kipo-api/kipi/patUtiModInfoSearchSevice/getPubFullTextInfoSearch",
        {"applicationNumber": appl_no, "ServiceKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "item")
    if not items:
        log.info("    공개전문: 없음")
        return

    data = xml_to_dict(items[0])
    save_json(data, os.path.join(folder, "05_공개전문정보.json"))
    log.info("    05_공개전문정보.json 저장")

    # 응답에 PDF URL 필드가 있으면 다운로드
    # (실제 필드명은 첫 실행 후 JSON 확인해서 아래에 추가)
    pdf_url = None
    for key in ("pubFullTextUrl", "fullTextUrl", "pdfUrl", "fileUrl", "docUrl"):
        pdf_url = items[0].findtext(key)
        if pdf_url:
            break

    if pdf_url:
        try:
            resp = requests.get(pdf_url, timeout=30)
            if resp.status_code == 200 and resp.content:
                pdf_path = os.path.join(folder, "05_공개전문.pdf")
                os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                with open(pdf_path, "wb") as f:
                    f.write(resp.content)
                log.info("    05_공개전문.pdf 저장")
        except Exception as e:
            log.warning(f"    PDF 다운로드 실패: {e}")


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────
def main():
    records = load_reg_numbers(EXCEL_FILE)[:MAX_COUNT]
    total = len(records)

    log.info("=" * 60)
    log.info("KIPRIS Plus API 수집기")
    log.info(f"  처리 예정: {total}건 → 결과: {OUTPUT_DIR}/")
    log.info("=" * 60)

    success, fail = 0, []

    for i, rec in enumerate(records):
        reg_no    = rec["등록번호"]
        log.info(f"\n[{i+1}/{total}] 등록번호: {reg_no}")

        # 등록번호 → 출원번호
        result = get_application_number(reg_no)
        time.sleep(DELAY_SEC)
        if not result:
            fail.append(reg_no)
            continue

        appl_no, title = result
        log.info(f"  출원번호: {appl_no} | 제목: {title[:50]}")

        folder = os.path.join(OUTPUT_DIR, f"{appl_no}_{safe_dirname(title)}")
        os.makedirs(folder, exist_ok=True)

        fetch_basic_info(appl_no, folder);      time.sleep(DELAY_SEC)
        fetch_office_actions(appl_no, folder);  time.sleep(DELAY_SEC)
        fetch_citations(appl_no, folder);       time.sleep(DELAY_SEC)
        fetch_claims_history(appl_no, folder);  time.sleep(DELAY_SEC)
        fetch_pub_pdf_info(appl_no, folder);    time.sleep(DELAY_SEC)

        success += 1

    log.info("\n" + "=" * 60)
    log.info(f"완료: 성공 {success}/{total}건")
    if fail:
        log.warning(f"실패 목록: {fail}")
    log.info(f"결과 경로: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
