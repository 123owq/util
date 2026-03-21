"""
extract_v4.py
개선사항:
  - 첨부 추출: 라인 기반으로 수정 (3개 모두 수집)
  - 비교표 헤더 행 구조 정리 (빈 컬럼 처리)
  - 최종 완성본
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

NOISE_PATTERNS = [
    r"^\d{2}-\d{4}-\d{7}$",
    r"^\d+/\d+$",
    r"^수신\s*:.*$",
    r"^-\s*아\s*래\s*-$",
]

def is_noise(text: str) -> bool:
    return any(re.match(p, text.strip()) for p in NOISE_PATTERNS)

# ─────────────────────────────────────────────
# 메타 추출
# ─────────────────────────────────────────────
def extract_meta(doc) -> dict:
    meta = {}
    page1_text = doc[0].get_text("text")

    m = re.search(r"호\s+(10-\d{4}-\d{7})", page1_text)
    if m:
        meta["출원번호"] = m.group(1)

    m = re.search(r"자(\d{4}\.\d{2}\.\d{2}\.)", page1_text)
    if m:
        meta["출원일자"] = m.group(1).rstrip(".")

    m = re.search(r"칭(.+?)(?=\n발송번호)", page1_text, re.DOTALL)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        meta["발명의명칭"] = re.sub(r"\s{2,}", " ", raw)

    for key, pat in [
        ("발송번호", r"발송번호:\s*([\S]+)"),
        ("발송일자", r"발송일자:\s*([\d.]+)"),
        ("제출기일", r"제출기일:\s*([\d.]+)"),
    ]:
        m = re.search(pat, page1_text)
        if m:
            meta[key] = m.group(1).rstrip(".")

    # 사람 필드: '명XXX\n주' 패턴
    person_values = re.findall(r"명([^\n]+(?:\n[^\n]{5,})?)\n주", page1_text)
    cleaned_persons = []
    for v in person_values:
        v = v.replace("\n", " ").strip()
        v = re.sub(r"\(특허고객번호:?\s*\d+\)", "", v).strip()
        v = re.sub(r"^\d+\)", "", v).strip()
        if v:
            cleaned_persons.append(v)

    if cleaned_persons:
        meta["출원인"] = cleaned_persons[0]
    if len(cleaned_persons) > 1:
        meta["대리인"] = cleaned_persons[1]
    if len(cleaned_persons) > 2:
        inventors = [p for p in cleaned_persons[2:] if re.match(r"^[가-힣]{2,5}$", p)]
        meta["발명자"] = inventors

    page2_text = doc[1].get_text("text")
    cited = re.findall(r"인용발명\s*\d+:\s*(.+)", page2_text)
    meta["인용발명"] = [c.strip() for c in cited]

    return meta

# ─────────────────────────────────────────────
# 첨부 추출 (라인 기반으로 수정)
# ─────────────────────────────────────────────
def extract_attachments(doc) -> list[str]:
    """5페이지에서 '첨부N  ...' 라인 추출"""
    attachments = []
    for page in doc:
        text = page.get_text("text")
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"첨부\d+\s+", line):
                # '첨부N  ' 접두사 제거
                value = re.sub(r"^첨부\d+\s+", "", line)
                # 끝에 '끝.' 제거
                value = re.sub(r"\s*끝\.?\s*$", "", value).strip()
                if value:
                    attachments.append(value)
    return attachments

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
                clean_tbl = [
                    [(cell or "").replace("\n", " ").strip() for cell in row]
                    for row in tbl
                ]
                cleaned.append(clean_tbl)
            tables_by_page[i] = cleaned
    return tables_by_page

def get_table_bboxes(pdf_path: Path) -> dict:
    bboxes = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            tbls = page.find_tables()
            if tbls:
                bboxes[i] = [tbl.bbox for tbl in tbls]
    return bboxes

def table_to_records(table: list[list[str]]) -> list[dict]:
    if not table or len(table) < 2:
        return []
    headers = table[0]
    return [
        {(h or f"col{i}"): v for i, (h, v) in enumerate(zip(headers, row))}
        for row in table[1:]
    ]

# ─────────────────────────────────────────────
# 비교표 구조화
# ─────────────────────────────────────────────
def parse_comparison_table(raw_table: list[list[str]]) -> dict:
    """
    p2 비교표 → 구조화된 dict
    컬럼: [구성번호, 청구항제1항, 인용발명1, 비고]
    """
    if not raw_table or len(raw_table) < 2:
        return {}

    # 헤더 행에서 실제 컬럼명 추출
    # raw_table[0] = ['청구항 제1항', '', '인용발명 1', '비고']
    col_names = ["구성", "청구항제1항", "인용발명1", "비고"]
    rows = []
    for row in raw_table[1:]:
        entry = {}
        for i, col in enumerate(col_names):
            entry[col] = row[i] if i < len(row) else ""
        rows.append(entry)

    return {
        "원본_헤더": raw_table[0],
        "rows": rows
    }

# ─────────────────────────────────────────────
# 심사결과 거절이유표
# ─────────────────────────────────────────────
def parse_rejection_table(tables_by_page: dict) -> list[dict]:
    for tbl in tables_by_page.get(1, []):
        if tbl and any("거절이유" in (c or "") for c in tbl[0]):
            return table_to_records(tbl)
    return []

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
# 메인 파싱
# ─────────────────────────────────────────────
def parse_oa(doc, tables_by_page: dict, table_bboxes: dict) -> dict:
    meta = extract_meta(doc)
    rejection_table = parse_rejection_table(tables_by_page)
    attachments = extract_attachments(doc)

    comparison_table = {}
    for tbl in tables_by_page.get(2, []):
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

                lbbox = line["bbox"]
                in_table = any(
                    lbbox[0] >= tb[0] - 2 and lbbox[1] >= tb[1] - 2 and
                    lbbox[2] <= tb[2] + 2 and lbbox[3] <= tb[3] + 2
                    for tb in page_bboxes
                )

                kind = classify_line(line_text)

                if kind == "section":
                    current_sub = None
                    continue

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

    out_path = OUTPUT_DIR / "OA_v4.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 요약
    lines = ["=== v4 최종 추출 결과 ===\n"]
    lines.append("[메타]")
    for k, v in result["meta"].items():
        lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("\n[심사결과 거절이유표]")
    for r in result["심사결과"]["거절이유표"]:
        lines.append(f"  {r}")
    lines.append(f"\n[거절이유 섹션: {len(result['구체적인거절이유']['sections'])}개]")
    for sub in result["구체적인거절이유"]["sections"]:
        lines.append(f"  {sub['header'][:60]}")
        lines.append(f"    content={len(sub['content'])}자, 비교표={sub['비교표'] is not None}")
    lines.append("\n[첨부]")
    for att in result["첨부"]:
        lines.append(f"  {att}")

    summary = "\n".join(lines)
    with open(OUTPUT_DIR / "v4_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary)

    print(summary)
    doc.close()
    return result

if __name__ == "__main__":
    main()
