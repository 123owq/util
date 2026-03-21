"""
extract_v5.py
OA.pdf, OA2.pdf, OA3.pdf, OA4.pdf 공통 추출기

v4 대비 개선사항:
  - 소섹션 패턴 다양화: 1-1., 1., 1) 형식 모두 지원
  - 비교표 동적 탐지: 페이지 하드코딩 제거, 헤더 키워드 기반
  - 인용발명 패턴: 공백+콜론 등 변형 대응
  - CLI: python extract_v5.py OA2.pdf
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
    r"^\d{2}-\d{4}-\d{7}$",
    r"^\d+/\d+$",
    r"^수신\s*:.*$",
    r"^-\s*아\s*래\s*-$",
    r"^수신\s+.+$",      # '수신  서울 송파구...' 형식
    r"^\d{5}$",          # 우편번호 (05854)
]

def is_noise(text: str) -> bool:
    return any(re.match(p, text.strip()) for p in NOISE_PATTERNS)

# ─────────────────────────────────────────────
# 헤더 분류 (다양한 소섹션 형식 지원)
# ─────────────────────────────────────────────
def classify_line(text: str) -> str:
    """
    'section'      : [심사결과], [구체적인 거절이유], [첨 부] 등
    'subsection'   : 1-1., 1-2., 2-1. 등 (대시 형식)
    'main_point'   : 1., 2., 3. 형식 (단순 번호+마침표)
    'sub_numbered' : 1), 2), 3) 형식 (괄호 형식)
    'normal'       : 일반 텍스트
    """
    t = text.strip()
    if re.match(r"^\[.+\]$", t):
        return "section"
    if re.match(r"^\d+-\d+\.", t):
        return "subsection"
    # '1. 이 출원...' 처럼 번호 다음 공백+텍스트 (문장 시작)
    if re.match(r"^\d+\.\s+[^\d]", t):
        return "main_point"
    if re.match(r"^\d+\)\s+", t):
        return "sub_numbered"
    return "normal"

# ─────────────────────────────────────────────
# 메타 추출
# ─────────────────────────────────────────────
def extract_meta(doc) -> dict:
    meta = {}
    page1_text = doc[0].get_text("text")

    # 출원번호
    m = re.search(r"호\s+(10-\d{4}-\d{7})", page1_text)
    if m:
        meta["출원번호"] = m.group(1)

    # 출원일자
    m = re.search(r"자(\d{4}\.\d{2}\.\d{2}\.)", page1_text)
    if m:
        meta["출원일자"] = m.group(1).rstrip(".")

    # 발명의명칭
    m = re.search(r"칭(.+?)(?=\n발송번호)", page1_text, re.DOTALL)
    if m:
        raw = m.group(1).replace("\n", " ").strip()
        meta["발명의명칭"] = re.sub(r"\s{2,}", " ", raw)

    # 발송번호/발송일자/제출기일
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
    if len(cleaned) > 2:
        inventors = [p for p in cleaned[2:] if re.match(r"^[가-힣]{2,5}$", p)]
        meta["발명자"] = inventors
    else:
        meta["발명자"] = []

    # 인용발명: 전체 텍스트에서 (공백+콜론 변형 대응)
    all_text = "\n".join(doc[pg].get_text("text") for pg in range(min(doc.page_count, 5)))
    cited = re.findall(r"인용발명\s*\d+\s*[：:]\s*(.+)", all_text)
    meta["인용발명"] = [c.strip() for c in cited if c.strip()]

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

def table_to_records(table: list[list[str]]) -> list[dict]:
    if not table or len(table) < 2:
        return []
    headers = table[0]
    return [{(h or f"col{i}"): v for i, (h, v) in enumerate(zip(headers, row))} for row in table[1:]]

# ─────────────────────────────────────────────
# 비교표 동적 탐지 (페이지 하드코딩 제거)
# ─────────────────────────────────────────────
COMPARISON_KEYWORDS = {"청구항", "인용발명", "비고", "구성"}

def is_comparison_table(tbl: list[list[str]]) -> bool:
    """비교표 조건: 4열, 3행+, 헤더에 청구항/인용발명 등 포함"""
    if not tbl or len(tbl) < 3 or len(tbl[0]) < 3:
        return False
    header_text = " ".join(str(c) for c in tbl[0])
    return any(kw in header_text for kw in COMPARISON_KEYWORDS)

def find_comparison_table(tables_by_page: dict):
    """문서 전체에서 비교표 탐색, 없으면 None"""
    for pg in sorted(tables_by_page.keys()):
        for tbl in tables_by_page[pg]:
            if is_comparison_table(tbl):
                return tbl
    return None

def parse_comparison_table(raw_table: list[list[str]]) -> dict:
    if not raw_table or len(raw_table) < 2:
        return {}
    header = raw_table[0]
    # 컬럼 이름 동적 할당
    col_keys = []
    for i, h in enumerate(header):
        if h:
            col_keys.append(h)
        else:
            col_keys.append(f"col{i}")
    rows = []
    for row in raw_table[1:]:
        entry = {col_keys[i]: (row[i] if i < len(row) else "") for i in range(len(col_keys))}
        rows.append(entry)
    return {"원본_헤더": header, "rows": rows}

# ─────────────────────────────────────────────
# 심사결과 거절이유표
# ─────────────────────────────────────────────
def parse_rejection_table(tables_by_page: dict) -> list[dict]:
    for tbl in tables_by_page.get(1, []):
        if tbl and any("거절이유" in (c or "") for c in tbl[0]):
            return table_to_records(tbl)
    return []

# ─────────────────────────────────────────────
# 첨부 추출
# ─────────────────────────────────────────────
def extract_attachments(doc) -> list[str]:
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
# 메인 파싱 (통합 소섹션 지원)
# ─────────────────────────────────────────────
def parse_oa(doc, tables_by_page: dict, table_bboxes: dict) -> dict:
    meta = extract_meta(doc)
    rejection_table = parse_rejection_table(tables_by_page)
    attachments = extract_attachments(doc)

    # 비교표 동적 탐지
    raw_comp = find_comparison_table(tables_by_page)
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

    # 심사대상청구항 추출
    for pg in range(doc.page_count):
        m = re.search(r"심사 대상 청구항\s*:\s*(.+)", doc[pg].get_text("text"))
        if m:
            result["심사결과"]["심사대상청구항"] = m.group(1).strip()
            break

    sections = result["구체적인거절이유"]["sections"]
    current_sub = None
    in_rejection_section = False  # [구체적인 거절이유] 섹션 진입 여부

    # 비교표를 첫 번째 비교 서술 섹션에 붙이기 위한 플래그
    comp_attached = False

    for page_num in range(1, doc.page_count + 1):
        page_text_simple = doc[page_num - 1].get_text("text")
        # 마지막 안내 페이지 스킵 (텍스트가 '안내' 관련만 있으면)
        if page_num == doc.page_count:
            if not any(kw in page_text_simple for kw in ["[구체적인", "[첨 부]", "거절이유"]):
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

                # 표 영역 내 스킵
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

                # 소섹션 헤더 감지 (1-1., 1., 1) 등)
                if kind in ("subsection", "main_point", "sub_numbered"):
                    current_sub = {
                        "header": line_text,
                        "content": "",
                        "비교표": None,
                    }
                    sections.append(current_sub)
                    continue

                if in_table:
                    continue

                if current_sub is not None:
                    current_sub["content"] += line_text + "\n"
                # in_rejection_section이지만 현재 sub가 없는 경우: 섹션 앞 공통 텍스트
                # → 별도 처리 안 함 (섹션 전 도입부는 버림)

    # 비교표 붙이기: 인용발명이 언급된 첫 번째 섹션에 붙임
    if comparison_table:
        for sub in sections:
            if "인용발명" in sub.get("content", "") or sub.get("header", "").startswith("3"):
                sub["비교표"] = comparison_table
                break
        # 못 붙인 경우 첫 섹션에라도 붙임
        if all(s["비교표"] is None for s in sections) and sections:
            sections[0]["비교표"] = comparison_table

    # content 정리
    for sub in sections:
        sub["content"] = sub["content"].strip()

    return result

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def process(pdf_path: Path):
    stem = pdf_path.stem  # OA2, OA3, OA4

    doc = fitz.open(pdf_path)
    tables_by_page = extract_tables(pdf_path)
    table_bboxes = get_table_bboxes(pdf_path)
    result = parse_oa(doc, tables_by_page, table_bboxes)

    # JSON 저장
    out_json = OUTPUT_DIR / f"{stem}_v5.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 요약
    lines = [f"=== {stem} v5 추출 결과 ===\n"]
    lines.append("[메타]")
    for k, v in result["meta"].items():
        lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append(f"\n[심사결과]")
    lines.append(f"  심사대상청구항: {result['심사결과']['심사대상청구항']}")
    lines.append(f"  거절이유표: {len(result['심사결과']['거절이유표'])}개 항목")
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
    summary_path = OUTPUT_DIR / f"{stem}_v5_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(summary)
    print(f"\n저장: {out_json}\n")
    doc.close()
    return result


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["OA2.pdf", "OA3.pdf", "OA4.pdf"]
    for fname in targets:
        process(Path(fname))
