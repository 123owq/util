"""
extract_v6.py - 100% 정확도 목표 공통 추출기

v5 대비 개선사항:
  - 소섹션 '5)' 단독 줄 처리 (^\d+\)\s*$ 패턴 추가)
  - 인용발명 중복 제거 (dict.fromkeys)
  - 비교표 위치: 섹션별 페이지 추적 후 가장 가까운 섹션에 붙임
  - content 단어 분리 줄 병합: 짧은 단어 줄 이어붙임
  - OA.pdf도 포함한 전체 파일 공통 처리
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import fitz
import pdfplumber
import json
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 노이즈 필터
# ─────────────────────────────────────────────
NOISE_PATTERNS = [
    r"^\d{2}-\d{4}-\d{7}$",   # 출원번호 단독 줄
    r"^\d+/\d+$",              # 페이지번호
    r"^수신\s*:.*$",
    r"^수신\s+.+$",            # 수신  서울 송파구...
    r"^-\s*아\s*래\s*-$",
    r"^\d{5}$",                # 우편번호
]

def is_noise(text: str) -> bool:
    return any(re.match(p, text.strip()) for p in NOISE_PATTERNS)

# ─────────────────────────────────────────────
# 헤더 분류 (전 유형 지원)
# ─────────────────────────────────────────────
def classify_line(text: str) -> str:
    t = text.strip()
    if re.match(r"^\[.+\]$", t):
        return "section"
    if re.match(r"^\d+-\d+\.", t):
        return "subsection"       # 1-1., 2-1. 형식
    if re.match(r"^\d+\.\s+[^\d]", t):
        return "main_point"       # 1. 내용... 형식
    if re.match(r"^\d+\)\s+", t):
        return "sub_numbered"     # 1) 내용... 형식 (공백 있음)
    if re.match(r"^\d+\)\s*$", t):
        return "sub_numbered"     # 5) 단독 줄 형식
    return "normal"

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

    # 사람 필드
    person_values = re.findall(r"명([^\n]+(?:\n[^\n]{5,})?)\n주", page1_text)
    cleaned = []
    for v in person_values:
        v = v.replace("\n", " ").strip()
        v = re.sub(r"\(특허고객번호:?\s*\d+\)", "", v).strip()
        v = re.sub(r"^\d+\)", "", v).strip()
        if v:
            cleaned.append(v)

    if cleaned:
        meta["출원인"] = cleaned[0]
    if len(cleaned) > 1:
        meta["대리인"] = cleaned[1]
    meta["발명자"] = [p for p in cleaned[2:] if re.match(r"^[가-힣]{2,5}$", p)] if len(cleaned) > 2 else []

    # 인용발명 (전체 텍스트, 중복 제거)
    all_text = "\n".join(doc[pg].get_text("text") for pg in range(min(doc.page_count, 5)))
    cited_raw = re.findall(r"인용발명\s*\d+\s*[：:]\s*(.+)", all_text)
    # 중복 제거 (순서 유지)
    seen = set()
    cited_clean = []
    for c in cited_raw:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            cited_clean.append(c)
    meta["인용발명"] = cited_clean

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
            cleaned = [
                [[(c or "").replace("\n", " ").strip() for c in row] for row in tbl]
                for tbl in raw
            ]
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

def table_to_records(table):
    if not table or len(table) < 2:
        return []
    headers = table[0]
    return [{(h or f"col{i}"): v for i, (h, v) in enumerate(zip(headers, row))} for row in table[1:]]

# ─────────────────────────────────────────────
# 비교표 동적 탐지
# ─────────────────────────────────────────────
COMPARISON_KEYWORDS = {"청구항", "인용발명", "비고", "구성"}

def is_comparison_table(tbl: list) -> bool:
    if not tbl or len(tbl) < 3 or len(tbl[0]) < 3:
        return False
    header_text = " ".join(str(c) for c in tbl[0])
    return any(kw in header_text for kw in COMPARISON_KEYWORDS)

def find_comparison_table_with_page(tables_by_page: dict):
    """비교표 탐색 → (page_num, table) 반환"""
    for pg in sorted(tables_by_page.keys()):
        for tbl in tables_by_page[pg]:
            if is_comparison_table(tbl):
                return pg, tbl
    return None, None

def parse_comparison_table(raw_table: list) -> dict:
    if not raw_table or len(raw_table) < 2:
        return {}
    header = raw_table[0]
    col_keys = [h if h else f"col{i}" for i, h in enumerate(header)]
    rows = [{col_keys[i]: (row[i] if i < len(row) else "") for i in range(len(col_keys))} for row in raw_table[1:]]
    return {"원본_헤더": header, "rows": rows}

# ─────────────────────────────────────────────
# content 단어 분리 줄 병합 (OA3 5) 케이스)
# ─────────────────────────────────────────────
def merge_fragmented_content(content: str) -> str:
    """
    PDF 렌더링으로 인해 단어 단위로 분리된 줄들을 병합.
    기준: 줄 길이가 짧고(15자 미만) 문장 종결 부호 없으면 이전 줄에 이어붙임.
    단, 새로운 번호 패턴 시작은 새 줄 유지.
    """
    lines = content.split("\n")
    if not lines:
        return content

    merged = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 새 번호 패턴이면 항상 새 줄
        if re.match(r"^\d+[\.\)]\s*", line):
            merged.append(line)
        # 짧은 줄 (단어 단위 분리 의심)이고 이전 줄이 있으면 이어붙임
        elif merged and len(line) <= 15 and not re.search(r"[.。다]$", merged[-1]):
            merged[-1] += " " + line
        else:
            merged.append(line)
    return "\n".join(merged)

# ─────────────────────────────────────────────
# 심사결과 거절이유표
# ─────────────────────────────────────────────
def parse_rejection_table(tables_by_page: dict) -> list:
    for tbl in tables_by_page.get(1, []):
        if tbl and any("거절이유" in (c or "") for c in tbl[0]):
            return table_to_records(tbl)
    return []

# ─────────────────────────────────────────────
# 첨부 추출
# ─────────────────────────────────────────────
def extract_attachments(doc) -> list:
    attachments = []
    for page in doc:
        for line in page.get_text("text").split("\n"):
            line = line.strip()
            if re.match(r"첨부\d+\s+", line):
                value = re.sub(r"^첨부\d+\s+", "", line)
                value = re.sub(r"\s*끝\.?\s*$", "", value).strip()
                if value:
                    attachments.append(value)
    return attachments

# ─────────────────────────────────────────────
# 메인 파싱
# ─────────────────────────────────────────────
def parse_oa(doc, tables_by_page: dict, table_bboxes: dict) -> dict:
    meta = extract_meta(doc)
    rejection_table = parse_rejection_table(tables_by_page)
    attachments = extract_attachments(doc)

    comp_page, raw_comp = find_comparison_table_with_page(tables_by_page)
    comparison_table = parse_comparison_table(raw_comp) if raw_comp else None

    result = {
        "meta": meta,
        "심사결과": {
            "심사대상청구항": "",
            "거절이유표": rejection_table,
        },
        "구체적인거절이유": {
            "sections": []
        },
        "첨부": attachments,
    }

    # 심사대상청구항
    for pg in range(doc.page_count):
        m = re.search(r"심사 대상 청구항\s*:\s*(.+)", doc[pg].get_text("text"))
        if m:
            result["심사결과"]["심사대상청구항"] = m.group(1).strip()
            break

    sections = result["구체적인거절이유"]["sections"]
    current_sub = None
    in_rejection_section = False

    for page_num in range(1, doc.page_count + 1):
        page_text_simple = doc[page_num - 1].get_text("text")
        # 마지막 안내 페이지 스킵
        if page_num == doc.page_count:
            if not any(kw in page_text_simple for kw in ["[구체적인", "[첨 부]", "거절이유", "1-1.", "1)"]):
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
                    if line_text == "[구체적인 거절이유]":
                        in_rejection_section = True
                    else:
                        in_rejection_section = False
                    current_sub = None
                    continue

                if not in_rejection_section:
                    continue

                if kind in ("subsection", "main_point", "sub_numbered"):
                    current_sub = {
                        "header": line_text,
                        "content": "",
                        "비교표": None,
                        "_page": page_num,
                    }
                    sections.append(current_sub)
                    continue

                if in_table:
                    continue

                if current_sub is not None:
                    current_sub["content"] += line_text + "\n"

    # 비교표 붙이기: comp_page와 같거나 이전 페이지의 마지막 섹션에
    if comparison_table and comp_page is not None:
        # comp_page 이전까지의 마지막 섹션 or comp_page와 같은 페이지 섹션 중 마지막
        target = None
        for sub in sections:
            if sub.get("_page", 0) <= comp_page:
                target = sub
            else:
                break
        if target:
            target["비교표"] = comparison_table
        elif sections:
            sections[0]["비교표"] = comparison_table

    # content 정리 및 _page 제거
    for sub in sections:
        content = sub["content"].strip()
        sub["content"] = merge_fragmented_content(content)
        sub.pop("_page", None)

    return result

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def process(pdf_path: Path):
    stem = pdf_path.stem
    doc = fitz.open(pdf_path)
    tables_by_page = extract_tables(pdf_path)
    table_bboxes = get_table_bboxes(pdf_path)
    result = parse_oa(doc, tables_by_page, table_bboxes)

    out_json = OUTPUT_DIR / f"{stem}_v6.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines = [f"=== {stem} v6 추출 결과 ===\n"]
    lines.append("[메타]")
    for k, v in result["meta"].items():
        lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append(f"\n[심사결과]")
    lines.append(f"  심사대상청구항: {result['심사결과']['심사대상청구항']}")
    lines.append(f"  거절이유표: {len(result['심사결과']['거절이유표'])}개")
    for r in result["심사결과"]["거절이유표"]:
        lines.append(f"    {r}")
    lines.append(f"\n[거절이유 섹션: {len(result['구체적인거절이유']['sections'])}개]")
    for sub in result["구체적인거절이유"]["sections"]:
        has_tbl = sub["비교표"] is not None
        lines.append(f"  [{sub['header'][:60]}]")
        lines.append(f"    content={len(sub['content'])}자, 비교표={has_tbl}")
    lines.append(f"\n[첨부]")
    for att in result["첨부"]:
        lines.append(f"  {att}")

    summary = "\n".join(lines)
    with open(OUTPUT_DIR / f"{stem}_v6_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary)
    print(summary)
    print(f"\n저장: {out_json}\n{'='*60}\n")
    doc.close()
    return result


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["OA.pdf", "OA2.pdf", "OA3.pdf", "OA4.pdf"]
    for fname in targets:
        process(Path(fname))
