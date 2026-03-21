"""
extract_v1.py
목적: OA.pdf 폰트 플래그 진단 + 기본 섹션 추출 + JSON 저장
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import fitz  # PyMuPDF
import pdfplumber
import json
import re
from pathlib import Path
from collections import Counter

PDF_PATH = Path("OA.pdf")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 1. 폰트 플래그 진단 (어떤 플래그가 소제목인지 확인)
# ─────────────────────────────────────────────
def diagnose_fonts(doc):
    """페이지별 span 정보 수집해서 폰트/사이즈/플래그 분포 확인"""
    records = []
    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = ""
                for span in line["spans"]:
                    line_text += span["text"]
                line_text = line_text.strip()
                if not line_text:
                    continue
                # 첫 span의 플래그/폰트로 대표
                span = line["spans"][0]
                records.append({
                    "page": page_num,
                    "text": line_text[:80],
                    "font": span["font"],
                    "size": round(span["size"], 2),
                    "flags": span["flags"],
                    "bold": bool(span["flags"] & (1 << 4)),
                    "italic": bool(span["flags"] & (1 << 1)),
                    "underline": bool(span["flags"] & (1 << 2)),
                })
    return records

# ─────────────────────────────────────────────
# 2. 헤더 감지 기준 결정 함수
# ─────────────────────────────────────────────
def is_header(span_info: dict, line_text: str) -> str | None:
    """
    헤더 종류 반환:
    - 'section'  : [심사결과] 등 대괄호 섹션
    - 'subsection': 1-1. 형식 소섹션
    - None       : 일반 텍스트
    """
    text = line_text.strip()
    if re.match(r"^\[.+\]$", text):
        return "section"
    if re.match(r"^\d+-\d+\.", text):
        return "subsection"
    return None

# ─────────────────────────────────────────────
# 3. 표 추출 (pdfplumber, 2페이지)
# ─────────────────────────────────────────────
def extract_tables_from_pdf(pdf_path: Path) -> dict[int, list]:
    """페이지별 표 추출. 셀 내 줄바꿈 정리."""
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
                        if cell is None:
                            clean_row.append("")
                        else:
                            clean_row.append(cell.replace("\n", " ").strip())
                    clean_tbl.append(clean_row)
                cleaned.append(clean_tbl)
            tables_by_page[i] = cleaned
    return tables_by_page

# ─────────────────────────────────────────────
# 4. 메인 파싱 (헤더-콘텐츠 매핑)
# ─────────────────────────────────────────────
def parse_oa(doc, tables_by_page: dict) -> dict:
    result = {
        "meta": {},
        "sections": []
    }

    # 메타 정보 정규식 패턴 (1페이지)
    meta_patterns = {
        "출원번호": r"출\s*원\s*번\s*호\s+([\d\-]+)",
        "출원일자": r"출\s*원\s*일\s*자\s+([\d.]+)",
        "발명의명칭": r"발\s*명\s*의\s*명\s*칭\s+(.+)",
        "발송번호": r"발송번호:\s*([\S]+)",
        "발송일자": r"발송일자:\s*([\d.]+)",
        "제출기일": r"제출기일:\s*([\d.]+)",
    }

    full_text_by_page = {}
    for page_num, page in enumerate(doc, start=1):
        full_text_by_page[page_num] = page.get_text("text")

    # 메타 추출 (1페이지 텍스트에서)
    page1_text = full_text_by_page.get(1, "")
    for key, pattern in meta_patterns.items():
        m = re.search(pattern, page1_text, re.DOTALL)
        if m:
            result["meta"][key] = m.group(1).strip()

    # 발명자 추출 (반복 필드)
    inventors = re.findall(r"발\s*명\s*자\s*성\s*명\s+(\S+)", page1_text)
    result["meta"]["발명자"] = inventors

    # 출원인
    m = re.search(r"출\s*원\s*인\s*성\s*명\s+(.+?)(?:특허고객번호|\n)", page1_text)
    if m:
        result["meta"]["출원인"] = m.group(1).strip()

    # 대리인
    m = re.search(r"대\s*리\s*인\s*성\s*명\s+(\S+)", page1_text)
    if m:
        result["meta"]["대리인"] = m.group(1).strip()

    # 인용발명 추출
    all_text = "\n".join(full_text_by_page.values())
    cited = re.findall(r"인용발명\s*\d+:\s*(.+)", all_text)
    result["meta"]["인용발명"] = [c.strip() for c in cited]

    # 섹션/서브섹션 파싱
    current_section = None
    current_subsection = None

    for page_num, page in enumerate(doc, start=1):
        if page_num == 6:  # 안내 페이지 스킵
            continue

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

                htype = is_header(spans[0], line_text)

                if htype == "section":
                    # 새 대섹션 시작
                    current_section = {
                        "header": line_text,
                        "content": "",
                        "subsections": [],
                        "tables": tables_by_page.get(page_num, []) if line_text == "[구체적인 거절이유]" else []
                    }
                    result["sections"].append(current_section)
                    current_subsection = None

                elif htype == "subsection":
                    # 새 소섹션 시작
                    current_subsection = {
                        "header": line_text,
                        "content": "",
                        "table": None
                    }
                    # 비교표 붙이기 (1-1 항목에만 표가 있음)
                    if line_text.startswith("1-1.") and page_num in tables_by_page:
                        current_subsection["table"] = tables_by_page[page_num]
                    if current_section:
                        current_section["subsections"].append(current_subsection)

                else:
                    # 일반 텍스트 → 현재 컨텍스트에 추가
                    if current_subsection:
                        current_subsection["content"] += line_text + "\n"
                    elif current_section:
                        current_section["content"] += line_text + "\n"

    # content 정리
    for sec in result["sections"]:
        sec["content"] = sec["content"].strip()
        for sub in sec.get("subsections", []):
            sub["content"] = sub["content"].strip()

    return result


# ─────────────────────────────────────────────
# 5. 진단 보고서 출력
# ─────────────────────────────────────────────
def print_font_summary(records):
    print("\n=== 폰트 분포 (font x size x flags) ===")
    counter = Counter((r["font"], r["size"], r["flags"]) for r in records)
    for (font, size, flags), cnt in counter.most_common(15):
        bold = bool(flags & (1 << 4))
        underline = bool(flags & (1 << 2))
        print(f"  [{cnt:3d}x] font={font}, size={size}, flags={flags} (bold={bold}, ul={underline})")

    print("\n=== 볼드/밑줄 텍스트 샘플 ===")
    for r in records:
        if r["bold"] or r["underline"]:
            print(f"  p{r['page']} | bold={r['bold']} ul={r['underline']} | {r['text'][:70]}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    doc = fitz.open(PDF_PATH)
    print(f"PDF 로드: {PDF_PATH}, 페이지 수: {doc.page_count}")

    # 진단
    records = diagnose_fonts(doc)
    print_font_summary(records)

    # 진단 결과 JSON 저장
    diag_path = OUTPUT_DIR / "OA_v1_fontdiag.json"
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n진단 결과 저장: {diag_path}")

    # 표 추출
    tables_by_page = extract_tables_from_pdf(PDF_PATH)
    print(f"\n표 발견 페이지: {list(tables_by_page.keys())}")
    for pg, tbls in tables_by_page.items():
        for i, tbl in enumerate(tbls):
            print(f"  p{pg} 표{i+1}: {len(tbl)}행 x {len(tbl[0]) if tbl else 0}열")

    # 파싱
    result = parse_oa(doc, tables_by_page)

    # JSON 저장
    out_path = OUTPUT_DIR / "OA_v1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n추출 결과 저장: {out_path}")

    # 구조 요약 출력
    print(f"\n=== 추출 구조 요약 ===")
    print(f"메타 필드: {list(result['meta'].keys())}")
    for sec in result["sections"]:
        print(f"  [{sec['header']}] content={len(sec['content'])}자, subsections={len(sec['subsections'])}")
        for sub in sec["subsections"]:
            has_table = sub["table"] is not None
            print(f"    └ {sub['header'][:50]} | content={len(sub['content'])}자 | table={has_table}")

    doc.close()
    return result, records

if __name__ == "__main__":
    main()
