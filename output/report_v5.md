# 다중 OA 추출 v5 보고서

## 버전 목적
OA.pdf 전용이었던 v4를 OA2.pdf / OA3.pdf / OA4.pdf 로 확장.
섹션 번호 형식 다양화, 비교표 동적 탐지, in_rejection_section 플래그 도입.

---

## 생성 파일

| 파일 | 설명 |
|---|---|
| `extract_v5.py` | 다중 PDF 공통 추출기 |
| `output/OA_v5.json` | OA.pdf 추출 결과 |
| `output/OA2_v5.json` | OA2.pdf 추출 결과 |
| `output/OA3_v5.json` | OA3.pdf 추출 결과 |
| `output/OA4_v5.json` | OA4.pdf 추출 결과 |
| `output/OA*_v5_summary.txt` | 각 파일 요약 |

---

## 핵심 코드 로직

### 소섹션 형식 다양화 (classify_line)

4종 섹션 번호 형식을 한 함수에서 처리:
```python
def classify_line(text: str) -> str:
    t = text.strip()
    if re.match(r"^\[.+\]$", t):         return "section"       # [심사결과]
    if re.match(r"^\d+-\d+\.", t):        return "subsection"    # 1-1. (OA, OA4)
    if re.match(r"^\d+\.\s+[^\d]", t):   return "main_point"    # 1. 이 출원... (OA2, OA4)
    if re.match(r"^\d+\)\s+", t):        return "sub_numbered"  # 1) 청구항... (OA3)
    return "normal"
```

### 비교표 동적 탐지

페이지 하드코딩(p2 고정) 제거 → 키워드 기반 탐색:
```python
COMPARISON_KEYWORDS = {"청구항", "인용발명", "비고", "구성"}

def is_comparison_table(tbl):
    if not tbl or len(tbl) < 3 or len(tbl[0]) < 3: return False
    header_text = " ".join(str(c) for c in tbl[0])
    return any(kw in header_text for kw in COMPARISON_KEYWORDS)
```

### [구체적인거절이유] 섹션 진입 플래그

```python
in_rejection_section = False

if kind == "section":
    if line_text == "[구체적인 거절이유]":
        in_rejection_section = True
    else:
        in_rejection_section = False
    current_sub = None
    continue

if not in_rejection_section:
    continue
```

---

## 추출 결과 요약

### OA.pdf (v5)
- 메타: 10개 필드 완전 추출 ✅
- 섹션: 9개 (1. 서론 + 1-1. ~ 1-8.) ✅
- 비교표: 1-1. 섹션에 부착 ✅
- 첨부: 3개 ✅

### OA2.pdf (v5)
- 메타: 10개 필드 완전 추출 ✅
- 거절이유표: 3개 ✅
- 섹션: 3개 (1. / 2. / 3.) ✅
- 비교표: 3. 섹션에 부착 ✅
- 첨부: 1개 ✅

### OA3.pdf (v5) — 미완
- 메타: 10개 필드 완전 추출 ✅
- 섹션: **5개** (6개 중 `5)` 누락 ❌)
  - OA3 p3에서 `5)` 가 단독 줄로 렌더링되고 이후 내용이 단어 단위로 분리되어 인식 실패
- 비교표: 없음 (OA3에는 비교표 미존재) ✅
- 첨부: 2개 ✅

### OA4.pdf (v5)
- 메타: 9개 필드 — 인용발명 **중복** (`WO2017/130956` 2회) ❌
- 섹션: 13개 정확히 추출 ✅
- 비교표: 2-1. 섹션에 부착 ✅ (페이지 기준 정확)
- 첨부: 2개 ✅

---

## 잔여 문제 (→ v6 수정 대상)

| 파일 | 문제 | 원인 |
|---|---|---|
| OA3 | `5)` 섹션 누락 | `5)` 단독 줄 패턴 미지원 (공백 없는 `^\d+\)$`) |
| OA3 | `5)` 내용 단어 분리 | PDF 렌더링으로 단어마다 줄 분리 |
| OA4 | 인용발명 중복 | 동일 패턴이 문서 내 2회 등장, 중복 제거 미구현 |

---

## 버전별 개선 히스토리

| 버전 | 대상 PDF | 주요 변경 | 해결된 문제 |
|---|---|---|---|
| v1~v4 | OA.pdf | 기본 추출, 메타, 표, 첨부 | OA.pdf 100% 완성 |
| v5 | OA~OA4 | 다중 PDF 지원, classify_line 확장, 동적 비교표 | OA2, OA4 완성. OA3 일부 미완 |

---

## PDF별 섹션 형식

| PDF | 섹션 형식 | 예시 |
|---|---|---|
| OA.pdf | `1.` + `1-1.` | `1. 이 출원의 ...`, `1-1. 청구항 제1항에 대한...` |
| OA2.pdf | `1.` `2.` `3.` | `1. 이 출원은 발명의 설명의...` |
| OA3.pdf | `1)` `2)` … `6)` | `1) 청구항 1 발명은...` |
| OA4.pdf | `1.` + `1-1.` `1-2.` + `2.`... | 복합 형식 |
