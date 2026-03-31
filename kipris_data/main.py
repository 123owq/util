import os       # 경로 조합용
import time     # API 호출 간격용
import logging  # 로그 설정용
from datetime import datetime  # 로그 파일명에 날짜 사용

from .config import EXCEL_FILE, OUTPUT_DIR, DONE_FILE, MAX_COUNT, DELAY_SEC  # 설정값
from .excel import load_reg_numbers                                 # 엑셀 로더
from .utils import safe_dirname                                     # 폴더명 정제
from .collectors import (           # 각 API 수집 함수
    get_application_number,
    fetch_patent_pdf,
    fetch_office_actions,
    fetch_citations,
    fetch_claims_history,
)

# 로그 설정: 콘솔 + 날짜별 파일 동시 출력
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # 터미널 출력
        logging.FileHandler(
            f"kipris_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"      # 한글 로그 깨짐 방지
        )
    ]
)
log = logging.getLogger("KIPRIS_API")


def load_done() -> set[str]:
    """완료 기록 파일에서 등록번호 목록 로드"""
    if not os.path.exists(DONE_FILE):
        return set()
    with open(DONE_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}  # 빈 줄 제외


def mark_done(reg_no: str):
    """완료된 등록번호를 파일에 추가"""
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(reg_no + "\n")


def main():
    records  = load_reg_numbers(EXCEL_FILE)[:MAX_COUNT]  # 엑셀 로드 후 최대 건수 제한
    done_set = load_done()                               # 이미 완료된 등록번호 목록
    total    = len(records)

    log.info("=" * 60)
    log.info("KIPRIS Plus API 수집기")
    log.info(f"  처리 예정: {total}건 | 이미 완료: {len(done_set)}건 → {OUTPUT_DIR}/")
    log.info("=" * 60)

    success, skip, fail = 0, 0, []  # 성공 / 스킵 / 실패 카운트

    for i, rec in enumerate(records):
        reg_no = rec["등록번호"]

        # 이미 완료된 건은 건너뜀
        if reg_no in done_set:
            log.info(f"[{i+1}/{total}] 스킵 (완료됨): {reg_no}")
            skip += 1
            continue

        log.info(f"\n[{i+1}/{total}] 등록번호: {reg_no}")

        # 등록번호로 출원번호 조회
        result = get_application_number(reg_no)
        time.sleep(DELAY_SEC)
        if not result:
            fail.append(reg_no)
            continue

        appl_no, title = result
        log.info(f"  출원번호: {appl_no} | 제목: {title[:50]}")

        folder = os.path.join(OUTPUT_DIR, f"{appl_no}_{safe_dirname(title)}")  # 출원번호_발명명칭
        os.makedirs(folder, exist_ok=True)

        fetch_patent_pdf(appl_no, folder);      time.sleep(DELAY_SEC)
        fetch_office_actions(appl_no, folder);  time.sleep(DELAY_SEC)
        fetch_citations(appl_no, folder);       time.sleep(DELAY_SEC)
        fetch_claims_history(appl_no, folder);  time.sleep(DELAY_SEC)

        mark_done(reg_no)   # 완료 기록
        done_set.add(reg_no)  # 이번 실행 중 중복 방지용 메모리 반영
        success += 1

    # 최종 결과 요약
    log.info("\n" + "=" * 60)
    log.info(f"완료: 성공 {success} / 스킵 {skip} / 실패 {len(fail)} (전체 {total}건)")
    if fail:
        log.warning(f"실패 목록: {fail}")
    log.info(f"결과 경로: {os.path.abspath(OUTPUT_DIR)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
