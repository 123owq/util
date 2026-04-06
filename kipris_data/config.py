import os

# 이 파일 기준 kipris/ 폴더의 절대경로 → 어디서 실행하든 경로 고정
_HERE = os.path.dirname(os.path.abspath(__file__))

API_KEY    = "HiBTnxX0BjLDlpqvkt/GZDAiM9qU1Od6TTaJqKsK2DM="                   # KIPRIS Plus 인증키
EXCEL_FILE = os.path.join(_HERE, "한국타이어등록특허.xlsx")                         # 등록번호 목록 엑셀
OUTPUT_DIR = os.path.join(_HERE, "output")                                      # 결과 저장 폴더
DONE_FILE  = os.path.join(_HERE, "done.txt")                                    # 완료 기록 파일
MAX_COUNT  = 9999                      # 처리할 최대 건수
DELAY_SEC  = 0.5                                                                # API 호출 간격 (초)

BASE = "http://plus.kipris.or.kr"  # KIPRIS Plus API 베이스 URL
