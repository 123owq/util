# KIPRIS Plus API 수집기

## 폴더 구조

```
kipris/
  config.py       ← API 키, 경로 등 설정값
  api.py          ← HTTP 호출 + 재시도
  utils.py        ← XML 파싱, JSON 저장 유틸
  excel.py        ← 엑셀에서 등록번호 로드
  collectors.py   ← 각 API 수집 함수 (5개)
  main.py         ← 메인 루프
```

## 사전 준비

패키지 설치 (최초 1회)

```bash
pip install requests pandas python-calamine
```

## 실행 방법

`pdf_ex/` 폴더에서 실행

```bash
python -m kipris.main
```

건수 제한 (테스트용)

```bash
MAX_COUNT=5 python -m kipris.main
```

## 결과

```
kipris_api_output/
  {출원번호}_{발명명칭}/
    01_기본정보.json          ← 출원인, 출원일, IPC, 초록 등
    02_의견제출통지서.json    ← 거절이유통지 목록 (없으면 미생성)
    03_선행특허.json          ← 심사관 인용 선행문헌 (없으면 미생성)
    04_청구항변동이력.json    ← 청구항 보정 이력 (없으면 미생성)
    05_공개전문정보.json      ← 공개전문 PDF 경로 정보
    05_공개전문.pdf           ← 공개전문 PDF 파일
```

## 재실행 (이어받기)

완료된 등록번호는 `kipris_done.txt`에 자동 기록됩니다.
중간에 끊기거나 재실행해도 완료된 건은 자동으로 건너뜁니다.

처음부터 다시 받으려면 `kipris_done.txt` 삭제 후 실행하면 됩니다.

## 설정 변경

`config.py`에서 수정

| 항목 | 기본값 | 설명 |
|---|---|---|
| `EXCEL_FILE` | `20260323133300.xlsx` | 등록번호 목록 엑셀 |
| `OUTPUT_DIR` | `kipris_api_output` | 결과 저장 폴더 |
| `DELAY_SEC` | `0.5` | API 호출 간격 (초) |
