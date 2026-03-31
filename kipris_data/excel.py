import logging       # 로그 출력용
import pandas as pd  # 엑셀 로드용

log = logging.getLogger("KIPRIS_API")  # 이 모듈 전용 로거


def load_reg_numbers(path: str) -> list[dict]:
    """엑셀 파일에서 등록번호 목록을 읽어 dict 리스트로 반환"""
    df = pd.read_excel(path, header=7, engine="calamine", dtype=str)
    # header=7 → 8번째 행(1-indexed)이 컬럼명 행 (위에 제목/날짜 행들이 있음)
    # engine="calamine" → openpyxl이 스타일 오류로 실패하는 파일을 읽기 위해 사용
    # dtype=str → 등록번호 앞자리가 숫자라 int로 읽히는 것 방지

    df.columns = ["순번", "발명명칭", "등록번호", "등록일자"]  # 컬럼명 직접 지정 (엑셀 헤더가 한글이라 명시)
    df = df.dropna(subset=["등록번호"])                       # 등록번호가 빈 행 제거

    records = df[["발명명칭", "등록번호"]].to_dict("records")  # 필요한 컬럼만 dict 리스트로 변환
    log.info(f"엑셀 로드: {len(records)}건 ({path})")
    return records
