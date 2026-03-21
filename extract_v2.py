"""
extract_v2.py
개선사항:
  - 메타 필드: 공백 포함 정규식으로 출원인/대리인/발명자/발명명칭 추출
  - content 노이즈 제거: 페이지번호, 출원번호, '수신 :' 등
  - 1-1 content에서 표 텍스트 중복 제거
  - [첨 부] 섹션 파일 목록 수집
  - 심사결과 거절이유 표 (p1) 별도 파싱
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
# 노이즈 라인 필터
# ─────────────────────────────────────────────
NOISE_PATTERNS = [
    r"^\d{2}-\d{4}-\d{7}$",   # 출원번호 단독 줄 (10-2023-0008170)
    r"^\d+/\d+$",              # 페이지번호 (1/6, 2/6)
    r"^수신\s*:.*$",           # 수신 :
    r"^-\s*아\s*래\s*-$",     # - 아  래 -
]

def is_noise(text: str) -> bool:
    t = text.strip()
    for pat in NOISE_PATTERNS:
        if re.match(pat, t):
            return True
    return False

# ─────────────────────────────────────────────
# 메타 추출 (공백 포함 정규식)
# ─────────────────────────────────────────────
def extract_meta(doc) -> dict:
    meta = {}
    # 1페이지 전체 텍스트
    page1 = doc[0].get_text("text")

    # 출원번호
    m = re.search(r"출\s*원\s*번\s*호\s+([\d\-]+)", page1)
    if m:
        meta["출원번호"] = m.group(1).strip()

    # 출원일자
    m = re.search(r"출\s*원\s*일\s*자\s+([\d.]+)", page1)
    if m:
        meta["출원일자"] = m.group(1).strip()

    # 발명의명칭: 줄바꿈 포함 2줄까지
    m = re.search(r"발\s*명\s*의\s*명\s*칭\s+([\s\S]+?)(?:\n발송번호|\n\n)", page1)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        meta["발명의명칭"] = re.sub(r"\s{2,}", " ", raw)

    # 발송번호
    m = re.search(r"발송번호:\s*([\S]+)", page1)
    if m:
        meta["발송번호"] = m.group(1).rstrip(".")

    # 발송일자
    m = re.search(r"발송일자:\s*([\d.]+)", page1)
    if m:
        meta["발송일자"] = m.group(1).rstrip(".")

    # 제출기일
    m = re.search(r"제출기일:\s*([\d.]+)", page1)
    if m:
        meta["제출기일"] = m.group(1).rstrip(".")

    # 출원인 (공백 포함)
    m = re.search(r"출\s+원\s+인\s+성\s+명\s+(.+?)(?=주\s+소|\n대\s+리)", page1, re.DOTALL)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        raw = re.sub(r"\(특허고객번호:?\s*\d+\)", "", raw).strip()
        meta["출원인"] = re.sub(r"\s{2,}", " ", raw)

    # 대리인 (공백 포함)
    m = re.search(r"대\s+리\s+인\s+성\s+명\s+(\S+)", page1)
    if m:
        meta["대리인"] = m.group(1).strip()

    # 발명자 (반복)
    inventors = re.findall(r"발\s+명\s+자\s+성\s+명\s+(\S+)", page1)
    meta["발명자"] = inventors

    # 인용발명 (2페이지에서)
    page2 = doc[1].get_text("text")
    cited = re.findall(r"인용발명\s*\d+:\s*(.+)", page2)
    meta["인용발명"] = [c.strip() for c in cited]

    return meta

# ─────────────────────────────────────────────
# 표 추출 (pdfplumber)
# ─────────────────────────────────────────────
def extract_tables(pdf_path: Path) -> dict:
    """페이지별 표 목록 반환 (페이지 인덱스 1부터)"""
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
                    clean_row = [
                        (cell or "").replace("\n", " ").strip()
                        for cell in row
                    ]
                    clean_tbl.append(clean_row)
                cleaned.append(clean_tbl)
            tables_by_page[i] = cleaned
    return tables_by_page

def table_to_records(table: list[list[str]]) -> list[dict]:
    """표 → 헤더-row dict 리스트 변환 (첫 행이 헤더)"""
    if not table or len(table) < 2:
        return []
    headers = table[0]
    records = []
    for row in table[1:]:
        record = {}
        for h, v in zip(headers, row):
            if h:
                record[h] = v
        records.append(record)
    return records

# ─────────────────────────────────────────────
# pdfplumber 표 bbox 수집 (content 중복 제거용)
# ─────────────────────────────────────────────
def get_table_bboxes(pdf_path: Path) -> dict:
    """페이지별 표 bbox 목록"""
    bboxes = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            tbls = page.find_tables()
            if tbls:
                bboxes[i] = [tbl.bbox for tbl in tbls]
    return bboxes

# ─────────────────────────────────────────────
# 첨부 파일 목록 추출
# ─────────────────────────────────────────────
def extract_attachments(doc) -> list[str]:
    attachments = []
    for page in doc:
        text = page.get_text("text")
        matches = re.findall(r"첨부\d+\s+(.+)", text)
        attachments.extend([m.strip() for m in matches])
    return attachments

# ─────────────────────────────────────────────
# 심사결과 거절이유 표 파싱 (p1)
# ─────────────────────────────────────────────
def parse_rejection_table(tables_by_page: dict) -> list[dict]:
    """p1 표: 거절이유가 있는 부분 + 관련 법조항"""
    p1_tables = tables_by_page.get(1, [])
    for tbl in p1_tables:
        # 헤더에 '거절이유' 포함 여부 확인
        if tbl and any("거절이유" in (cell or "") for cell in tbl[0]):
            return table_to_records(tbl)
    return []

# ─────────────────────────────────────────────
# 헤더 감지
# ─────────────────────────────────────────────
def classify_line(text: str) -> str:
    """
    'section'    : [심사결과] 등
    'subsection' : 1-1. 형식
    'normal'     : 일반 텍스트
    """
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

    current_sub = None
    sections = result["구체적인거절이유"]["sections"]

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
                if not line_text:
                    continue
                if is_noise(line_text):
                    continue

                # 표 영역 안 텍스트 스킵 (content 중복 방지)
                # line bbox 확인
                line_bbox = line["bbox"]  # (x0, y0, x1, y1)
                in_table = False
                for tbbox in page_bboxes:
                    # 표 bbox 안에 line이 있으면 스킵
                    if (line_bbox[0] >= tbbox[0] - 2 and
                        line_bbox[1] >= tbbox[1] - 2 and
                        line_bbox[2] <= tbbox[2] + 2 and
                        line_bbox[3] <= tbbox[3] + 2):
                        in_table = True
                        break

                kind = classify_line(line_text)

                # [구체적인 거절이유] 이전 섹션 (심사결과 등) 스킵
                if kind == "section" and line_text != "[구체적인 거절이유]":
                    current_sub = None
                    continue

                if kind == "section" and line_text == "[구체적인 거절이유]":
                    current_sub = None
                    continue

                if kind == "subsection":
                    current_sub = {
                        "header": line_text,
                        "content": "",
                        "비교표": None,
                    }
                    # 1-1에는 비교표 첨부 (p2)
                    if line_text.startswith("1-1.") and 2 in tables_by_page:
                        # p2 tables 중 비교표(5행)
                        for tbl in tables_by_page[2]:
                            if len(tbl) >= 4:
                                current_sub["비교표"] = tbl
                                break
                    sections.append(current_sub)
                    continue

                # 일반 텍스트
                if in_table:
                    continue  # 표 안 텍스트는 스킵

                if current_sub is not None:
                    current_sub["content"] += line_text + "\n"

    # content 정리
    for sub in sections:
        sub["content"] = sub["content"].strip()

    return result

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    doc = fitz.open(PDF_PATH)
    print(f"[v2] PDF 로드: {PDF_PATH.name}, {doc.page_count}페이지")

    tables_by_page = extract_tables(PDF_PATH)
    table_bboxes = get_table_bboxes(PDF_PATH)

    print(f"표 발견 페이지: {list(tables_by_page.keys())}")
    for pg, tbls in tables_by_page.items():
        for i, tbl in enumerate(tbls):
            print(f"  p{pg} 표{i+1}: {len(tbl)}행 x {len(tbl[0]) if tbl else 0}열")

    result = parse_oa(doc, tables_by_page, table_bboxes)

    # 결과 저장
    out_path = OUTPUT_DIR / "OA_v2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out_path}")

    # 구조 요약
    print("\n=== 구조 요약 ===")
    print(f"메타: {json.dumps(result['meta'], ensure_ascii=False, indent=2)}")
    print(f"\n심사결과 거절이유표: {result['심사결과']['거절이유표']}")
    print(f"\n거절이유 섹션 수: {len(result['구체적인거절이유']['sections'])}")
    for sub in result["구체적인거절이유"]["sections"]:
        has_tbl = sub["비교표"] is not None
        print(f"  [{sub['header'][:55]}] content={len(sub['content'])}자, 비교표={has_tbl}")
    print(f"\n첨부: {result['첨부']}")

    doc.close()
    return result

if __name__ == "__main__":
    main()
