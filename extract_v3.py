"""
extract_v3.py
개선사항:
  - 메타 추출: 1페이지 특수 레이아웃(한글자씩 분리) 대응
    '명XXX\n주' 패턴으로 출원인/대리인/발명자 추출
    '호 XXX', '자YYYY.MM.DD.', '칭XXX' 패턴으로 번호/일자/명칭 추출
  - 첨부 "끝." 제거
  - 비교표: 헤더+레코드 구조로 변환 (dict 리스트)
  - 비교표 셀 내 불필요한 공백 제거
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import fitz
import pdfplumber
import json
import re
from pathlib import Path

PDF_PATH = Path("OA.pdf")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 노이즈 필터
# ─────────────────────────────────────────────
NOISE_PATTERNS = [
    r"^\d{2}-\d{4}-\d{7}$",
    r"^\d+/\d+$",
    r"^수신\s*:.*$",
    r"^-\s*아\s*래\s*-$",
]

def is_noise(text: str) -> bool:
    t = text.strip()
    return any(re.match(p, t) for p in NOISE_PATTERNS)

# ─────────────────────────────────────────────
# 메타 추출 (1페이지 특수 레이아웃 대응)
# ─────────────────────────────────────────────
def extract_meta(doc) -> dict:
    meta = {}
    page1_text = doc[0].get_text("text")

    # 1) 출원번호: '호 10-2023-0008170'
    m = re.search(r"호\s+(10-\d{4}-\d{7})", page1_text)
    if m:
        meta["출원번호"] = m.group(1)

    # 2) 출원일자: '자2023.01.19.'
    m = re.search(r"자(\d{4}\.\d{2}\.\d{2}\.)", page1_text)
    if m:
        meta["출원일자"] = m.group(1).rstrip(".")

    # 3) 발명의명칭: '칭시트고무 가공성...\n정량화 방법'
    m = re.search(r"칭(.+?)(?=\n발송번호)", page1_text, re.DOTALL)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        meta["발명의명칭"] = re.sub(r"\s{2,}", " ", raw)

    # 4) 발송번호/발송일자/제출기일
    for key, pat in [
        ("발송번호", r"발송번호:\s*([\S]+)"),
        ("발송일자", r"발송일자:\s*([\d.]+)"),
        ("제출기일", r"제출기일:\s*([\d.]+)"),
    ]:
        m = re.search(pat, page1_text)
        if m:
            meta[key] = m.group(1).rstrip(".")

    # 5) '명XXX\n주' 패턴으로 사람 필드 추출
    # 페이지1 텍스트에서 '명'으로 끝나는 레이블 다음 값들
    # 구조: "명한국타이어앤테크놀로지 주식회사 (특허고객번호: \n120120550993)\n주"
    #        "명한상수\n주"
    #        "명박해민\n주" 반복 4회
    person_values = re.findall(r"명([^\n]+(?:\n[^\n]{5,})?)\n주", page1_text)
    # 결과 예: ['한국타이어앤테크놀로지 주식회사 (특허고객번호: ', '120120550993)', '한상수', '박해민', ...]
    # 첫 번째: 출원인 (회사명)
    # 두 번째: 대리인
    # 나머지: 발명자들

    cleaned_persons = []
    for v in person_values:
        v = v.replace("\n", " ").strip()
        v = re.sub(r"\(특허고객번호:?\s*\d+\)", "", v).strip()
        v = re.sub(r"^\d+\)", "", v).strip()  # '120120550993)' 같은 잔여 제거
        if v:
            cleaned_persons.append(v)

    if cleaned_persons:
        meta["출원인"] = cleaned_persons[0]
    if len(cleaned_persons) > 1:
        meta["대리인"] = cleaned_persons[1]
    if len(cleaned_persons) > 2:
        # 한글 이름만 (2~4글자) 발명자로
        inventors = [p for p in cleaned_persons[2:] if re.match(r"^[가-힣]{2,5}$", p)]
        meta["발명자"] = inventors

    # 2페이지: 인용발명
    page2_text = doc[1].get_text("text")
    cited = re.findall(r"인용발명\s*\d+:\s*(.+)", page2_text)
    meta["인용발명"] = [c.strip() for c in cited]

    return meta

# ─────────────────────────────────────────────
# 표 추출
# ─────────────────────────────────────────────
def extract_tables(pdf_path: Path) -> dict:
    tables_by_page = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_tables()
            if not raw:
                continue
            cleaned = []
            for tbl in raw:
                clean_tbl = []
                for row in tbl:
                    clean_row = []
                    for cell in row:
                        cell_text = (cell or "").replace("\n", " ").strip()
                        # 단어 중간 불필요한 공백 제거 (예: '정련 부;' 유지, '시 트' → '시트')
                        # 단, 의도적 공백(셀 구분)은 유지
                        clean_row.append(cell_text)
                    clean_tbl.append(clean_row)
                cleaned.append(clean_tbl)
            tables_by_page[i] = cleaned
    return tables_by_page

def table_to_records(table: list[list[str]]) -> list[dict]:
    """첫 행 헤더 기준 dict 리스트 변환"""
    if not table or len(table) < 2:
        return []
    headers = [h for h in table[0]]
    records = []
    for row in table[1:]:
        record = {}
        for h, v in zip(headers, row):
            record[h if h else f"col_{len(record)}"] = v
        records.append(record)
    return records

def get_table_bboxes(pdf_path: Path) -> dict:
    bboxes = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            tbls = page.find_tables()
            if tbls:
                bboxes[i] = [tbl.bbox for tbl in tbls]
    return bboxes

# ─────────────────────────────────────────────
# 비교표 구조화 (p2, 5행 4열 → 구성별 dict)
# ─────────────────────────────────────────────
def parse_comparison_table(raw_table: list[list[str]]) -> dict:
    """
    원본: [[헤더행], [구성1행], [구성2행], [구성3행], [구성4행]]
    출력: {
        "헤더": [...],
        "rows": [{"구성": "구성 1", "청구항": "...", "인용발명1": "...", "비고": "..."}, ...]
    }
    """
    if not raw_table:
        return {}
    header = raw_table[0]  # ['청구항 제1항', '', '인용발명 1', '비고']
    rows = []
    for row in raw_table[1:]:
        entry = {}
        # 컬럼: [구성번호, 청구항내용, 인용발명1내용, 비고]
        entry["구성"] = row[0] if len(row) > 0 else ""
        entry["청구항제1항"] = row[1] if len(row) > 1 else ""
        entry["인용발명1"] = row[2] if len(row) > 2 else ""
        entry["비고"] = row[3] if len(row) > 3 else ""
        rows.append(entry)
    return {
        "컬럼": header,
        "rows": rows
    }

# ─────────────────────────────────────────────
# 첨부 파일 목록 추출
# ─────────────────────────────────────────────
def extract_attachments(doc) -> list[str]:
    attachments = []
    for page in doc:
        text = page.get_text("text")
        matches = re.findall(r"첨부\d+\s+(.+?)(?:\.?\s*(?:첨부\d+|$))", text)
        for m in matches:
            cleaned = m.strip().rstrip(". 끝")
            if "공개특허공보" in cleaned:
                attachments.append(cleaned.strip() + ".")
    return attachments

# ─────────────────────────────────────────────
# 헤더 분류
# ─────────────────────────────────────────────
def classify_line(text: str) -> str:
    t = text.strip()
    if re.match(r"^\[.+\]$", t):
        return "section"
    if re.match(r"^\d+-\d+\.", t):
        return "subsection"
    return "normal"

# ─────────────────────────────────────────────
# 심사결과 거절이유표
# ─────────────────────────────────────────────
def parse_rejection_table(tables_by_page: dict) -> list[dict]:
    p1_tables = tables_by_page.get(1, [])
    for tbl in p1_tables:
        if tbl and any("거절이유" in (cell or "") for cell in tbl[0]):
            return table_to_records(tbl)
    return []

# ─────────────────────────────────────────────
# 메인 파싱
# ─────────────────────────────────────────────
def parse_oa(doc, tables_by_page: dict, table_bboxes: dict) -> dict:
    meta = extract_meta(doc)
    rejection_table = parse_rejection_table(tables_by_page)
    attachments = extract_attachments(doc)

    # p2 비교표 파싱
    comparison_table = {}
    if 2 in tables_by_page:
        for tbl in tables_by_page[2]:
            if len(tbl) >= 4:
                comparison_table = parse_comparison_table(tbl)
                break

    result = {
        "meta": meta,
        "심사결과": {
            "심사대상청구항": "제1-10항",
            "거절이유표": rejection_table,
        },
        "구체적인거절이유": {
            "sections": []
        },
        "첨부": attachments,
    }

    sections = result["구체적인거절이유"]["sections"]
    current_sub = None

    for page_num in range(1, doc.page_count + 1):
        if page_num == 6:
            continue

        page = doc[page_num - 1]
        page_bboxes = table_bboxes.get(page_num, [])
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans = line["spans"]
                if not spans:
                    continue
                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text or is_noise(line_text):
                    continue

                # 표 영역 내 텍스트 스킵
                lbbox = line["bbox"]
                in_table = any(
                    lbbox[0] >= tb[0] - 2 and lbbox[1] >= tb[1] - 2 and
                    lbbox[2] <= tb[2] + 2 and lbbox[3] <= tb[3] + 2
                    for tb in page_bboxes
                )

                kind = classify_line(line_text)

                if kind == "section":
                    current_sub = None
                    continue  # [구체적인거절이유] 섹션헤더 자체는 스킵

                if kind == "subsection":
                    current_sub = {
                        "header": line_text,
                        "content": "",
                        "비교표": comparison_table if line_text.startswith("1-1.") else None,
                    }
                    sections.append(current_sub)
                    continue

                if in_table:
                    continue

                if current_sub is not None:
                    current_sub["content"] += line_text + "\n"

    # content 후처리
    for sub in sections:
        sub["content"] = sub["content"].strip()

    return result

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    doc = fitz.open(PDF_PATH)

    tables_by_page = extract_tables(PDF_PATH)
    table_bboxes = get_table_bboxes(PDF_PATH)
    result = parse_oa(doc, tables_by_page, table_bboxes)

    out_path = OUTPUT_DIR / "OA_v3.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 검증 출력 (UTF-8 파일로 저장)
    summary_lines = []
    summary_lines.append(f"=== v3 추출 결과 요약 ===\n")
    summary_lines.append(f"[메타]")
    for k, v in result["meta"].items():
        summary_lines.append(f"  {k}: {v}")
    summary_lines.append(f"\n[심사결과 거절이유표]")
    for row in result["심사결과"]["거절이유표"]:
        summary_lines.append(f"  {row}")
    summary_lines.append(f"\n[거절이유 섹션 {len(result['구체적인거절이유']['sections'])}개]")
    for sub in result["구체적인거절이유"]["sections"]:
        has_tbl = sub["비교표"] is not None
        summary_lines.append(f"  [{sub['header'][:60]}]")
        summary_lines.append(f"    content={len(sub['content'])}자, 비교표={has_tbl}")
    summary_lines.append(f"\n[첨부]")
    for att in result["첨부"]:
        summary_lines.append(f"  {att}")

    summary_text = "\n".join(summary_lines)
    with open(OUTPUT_DIR / "v3_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary_text)

    print(summary_text)
    doc.close()
    return result

if __name__ == "__main__":
    main()
