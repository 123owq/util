import os        # 경로 조합, 폴더 생성용
import logging  # 로그 출력용
import requests  # PDF 직접 다운로드용

from .config import API_KEY, BASE      # 인증키, 베이스 URL
from .api import api_get               # HTTP GET + 재시도 래퍼
from .utils import xml_to_dict, find_all, save_json  # XML 파싱, JSON 저장 유틸

log = logging.getLogger("KIPRIS_API")


def get_application_number(reg_no: str) -> tuple[str, str] | None:
    """등록번호 → (출원번호, 발명명칭). 실패 시 None."""
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

    appl_no = (items[0].findtext("applicationNumber") or "").strip()
    title   = (items[0].findtext("inventionTitle") or reg_no).strip()
    return (appl_no, title) if appl_no else None


def _download_pdf(url: str, path: str) -> bool:
    """URL에서 PDF 다운로드. 성공 여부 반환."""
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and resp.content:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(resp.content)
            return True
        log.warning(f"    PDF 다운로드 실패 (HTTP {resp.status_code}): {url}")
    except Exception as e:
        log.warning(f"    PDF 다운로드 오류: {e}")
    return False


def fetch_patent_pdf(appl_no: str, folder: str):
    """공개전문 PDF 다운로드 → 01_특허/"""
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

    sub = os.path.join(folder, "01_특허")
    os.makedirs(sub, exist_ok=True)

    # API 응답 JSON 저장 (참고용)
    save_json(xml_to_dict(items[0]), os.path.join(sub, "pub_info.json"))

    # PDF 다운로드
    pdf_url = items[0].findtext("path")
    if pdf_url:
        ok = _download_pdf(pdf_url, os.path.join(sub, "patent.pdf"))
        log.info(f"    01_특허/patent.pdf: {'저장' if ok else '실패'}")
    else:
        log.warning("    공개전문 PDF URL(path) 없음")


def fetch_office_actions(appl_no: str, folder: str):
    """의견제출통지서 PDF 다운로드 → 02_의견제출통지서/"""
    root = api_get(
        f"{BASE}/openapi/rest/IntermediateDocumentOPService/advancedSearchInfo",
        {"applicationNumber": appl_no, "patent": "true", "utility": "true", "accessKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "advancedSearchInfo")
    if not items:
        log.info("    의견제출통지서: 없음")
        return

    sub = os.path.join(folder, "02_의견제출통지서")
    os.makedirs(sub, exist_ok=True)

    for it in items:
        send_no = it.findtext("sendNumber") or "unknown"  # 발송번호를 파일명에 사용
        pdf_url = it.findtext("filePath")
        if not pdf_url:
            continue
        ok = _download_pdf(pdf_url, os.path.join(sub, f"oa_{send_no}.pdf"))
        log.info(f"    02_의견제출통지서/oa_{send_no}.pdf: {'저장' if ok else '실패'}")


def fetch_citations(appl_no: str, folder: str):
    """인용문헌 목록 저장 → 03_인용문헌/citations.json"""
    root = api_get(
        f"{BASE}/openapi/rest/CitationService/citationInfoV3",
        {"applicationNumber": appl_no, "accessKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "citationInfoV3")
    if not items:
        log.info("    인용문헌: 없음")
        return

    sub = os.path.join(folder, "03_인용문헌")
    os.makedirs(sub, exist_ok=True)

    save_json([xml_to_dict(it) for it in items], os.path.join(sub, "citations.json"))
    log.info(f"    03_인용문헌/citations.json: {len(items)}건 저장")


def fetch_claims_history(appl_no: str, folder: str):
    """보정이력 상세 저장 → 04_보정이력/claims_history.json"""
    root = api_get(
        f"{BASE}/openapi/rest/ClaimsChangeHistoryService/amendmentHistoryDetailInfo",
        {"applicationNumber": appl_no, "accessKey": API_KEY}
    )
    if root is None:
        return

    items = find_all(root, "amendmentHistoryDetailInfo")
    if not items:
        log.info("    보정이력: 없음")
        return

    sub = os.path.join(folder, "04_보정이력")
    os.makedirs(sub, exist_ok=True)

    save_json([xml_to_dict(it) for it in items], os.path.join(sub, "claims_history.json"))
    log.info(f"    04_보정이력/claims_history.json: {len(items)}건 저장")
