import time                          # 재시도 간 대기용
import logging                       # 로그 출력용
import requests                      # HTTP 요청용
import xml.etree.ElementTree as ET   # XML 파싱용

log = logging.getLogger("KIPRIS_API")  # 이 모듈 전용 로거


def api_get(url: str, params: dict, retries=3) -> ET.Element | None:
    """GET 요청 후 XML 루트 반환. 실패 시 최대 retries번 재시도."""
    for attempt in range(retries):                          # 재시도 횟수만큼 반복
        try:
            resp = requests.get(url, params=params, timeout=20)  # HTTP GET, 20초 타임아웃
            resp.raise_for_status()                              # 4xx/5xx면 예외 발생
            return ET.fromstring(resp.content)                   # 응답 바이트를 XML로 파싱 후 반환
        except Exception as e:
            log.warning(f"  [재시도 {attempt+1}/{retries}] {e}")  # 실패 내용 로그
            time.sleep(2)                                        # 2초 대기 후 재시도

    log.error(f"  API 호출 최종 실패: {url}")  # retries 소진 시 에러 로그
    return None                                # 실패 시 None 반환
