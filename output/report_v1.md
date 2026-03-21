# OA.pdf 추출 v1 보고서

## 버전 목적
PDF 폰트 플래그 진단 + 기본 섹션 추출 첫 시도

---

## 생성 파일

| 파일 | 설명 |
|---|---|
| `extract_v1.py` | v1 추출 코드 |
| `output/OA_v1.json` | 추출 결과 JSON |
| `output/OA_v1_fontdiag.json` | 폰트 플래그 진단 결과 |

---

## 핵심 코드 로직

### 폰트 플래그 진단
```python
def diagnose_fonts(doc):
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block["lines"]:
                span = line["spans"][0]
                {
                    "font": span["font"],
                    "size": round(span["size"], 2),
                    "flags": span["flags"],
                    "bold": bool(span["flags"] & (1 << 4)),
                    "underline": bool(span["flags"] & (1 << 2)),
                }
```

### 헤더 감지 기준
```python
def is_header(span_info, line_text):
    if re.match(r"^\[.+\]$", text):
        return "section"       # [심사결과] 등
    if re.match(r"^\d+-\d+\.", text):
        return "subsection"    # 1-1. 형식
    return None
```

### 표 추출 (pdfplumber)
```python
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        raw = page.extract_tables()
        # 셀 내 줄바꿈 정리
        cell.replace("\n", " ").strip()
```

### 메타 추출 (정규식)
```python
re.search(r"출\s*원\s*번\s*호\s+([\d\-]+)", page1_text)
re.search(r"발\s*명\s*자\s*성\s*명\s+(\S+)", page1_text)
```

---

## 추출 결과

### 폰트 분포 진단 결과 (핵심 발견)
| 폰트 | 크기 | flags | bold | underline | 빈도 |
|---|---|---|---|---|---|
| GulimChe | 11.03 | 4 | False | True | 186 |
| GulimChe | 9.95 | 4 | False | True | 52 |
| GulimChe | 15.95 | 4 | False | True | 3 |
| GulimChe | 23.98 | 4 | False | True | 1 |

**결론: 모든 텍스트 flags=4 (underline만) → 볼드 플래그로 헤더 구분 불가, 정규식+위치 기반 필요**

### 표 발견
- p1: 2행 x 3열 (심사결과 거절이유표)
- p2: 5행 x 4열 (청구항 vs 인용발명 1 비교표)

### JSON 구조
```json
{
  "meta": {
    "출원번호": "10-2023-0008170",
    "발송번호": "9-5-2025-045321288",
    "발송일자": "2025.05.12",
    "제출기일": "2025.07.12",
    "발명자": [],         ← 누락
    "인용발명": [3개]
  },
  "sections": [
    {"header": "[심사결과]", "content": "...", "subsections": []},
    {"header": "[구체적인 거절이유]", "subsections": [8개]},
    {"header": "[첨 부]", "content": ""}   ← 첨부 목록 누락
  ]
}
```

---

## 발견된 문제점

| # | 문제 | 원인 |
|---|---|---|
| 1 | 발명자/출원인/대리인 누락 | 1페이지가 2컬럼 표 구조 - 각 글자가 개별 줄로 분리됨 (`명박해민`, `명한상수`) |
| 2 | content에 노이즈 포함 | 페이지번호(`2/6`), 출원번호, `수신 :` 등이 섞임 |
| 3 | 비교표 텍스트가 content에 중복 | 표 영역 내 텍스트 필터링 없음 |
| 4 | [첨 부] 파일 목록 미수집 | 정규식 패턴 미적용 |
| 5 | 발명의명칭 누락 | 2줄 분리 패턴 미처리 |
| 6 | 볼드 구분 불가 | PDF 내 모든 텍스트가 동일한 flags=4 |

---

## 다음 버전(v2)에서 개선 예정
- 노이즈 필터 추가
- 표 bbox 기반 content 중복 제거
- 메타 정규식 개선
- 첨부 파일 목록 수집
