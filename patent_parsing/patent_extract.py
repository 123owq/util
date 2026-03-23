"""
patent_extract.py - 특허 공개/등록공보 PDF → JSON 변환기 (정보손실 0%)

구조:
  서지사항  : (11)(12)(21)(22)(43)(45)(51)(52)(54)(57)(71)(72)(74)
  청구범위  : 청구항 1, 2, 3 ...
  발명의설명: 섹션 헤더(size 10) + [NNNN] 단락번호 + 본문
  부호설명  : 도면 앞 페이지 참조번호 목록
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import fitz
import json
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 노이즈 판정
# ─────────────────────────────────────────────────────────────
FOOTER_FONTS = {"GulimChe", "Gulim"}

def is_footer(font: str, size: float, text: str) -> bool:
    base = font.split("-")[0]
    if base in FOOTER_FONTS:
        return True
    if re.match(r"^-\s*\d+\s*-$", text.strip()):
        return True
    # 공개특허/등록특허 반복 헤더
    if re.match(r"^(공개특허|등록특허)\s+\d{2}-\d{4}-\d{7}$", text.strip()):
        return True
    return False


# ─────────────────────────────────────────────────────────────
# 페이지 → 구조화 라인 목록
# ─────────────────────────────────────────────────────────────
def get_lines(page) -> list:
    """
    반환: [{ text, header(bool), para_num(bool), footer(bool) }]
    header   : font size ≈ 10.0 + BatangChe  → 섹션/소섹션 헤더
    para_num : Symbol font + [NNNN] 패턴     → 단락번호
    footer   : Gulim계 or 페이지번호         → 노이즈
    """
    result = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            sp = spans[0]
            font, size = sp["font"], sp["size"]

            footer   = is_footer(font, size, text)
            is_hdr   = (not footer) and abs(size - 10.0) < 0.3 and "BatangChe" in font
            is_pnum  = "Symbol" in font and bool(re.match(r"^\[\d{4}\]$", text))

            result.append({
                "text":      text,
                "header":    is_hdr,
                "para_num":  is_pnum,
                "footer":    footer,
            })
    return result


# ─────────────────────────────────────────────────────────────
# 서지사항
# ─────────────────────────────────────────────────────────────
def extract_biblio(doc) -> dict:
    # 1~2페이지 합쳐서 파싱 (CPC가 2페이지로 넘어가는 경우)
    p0 = doc[0].get_text("text")
    p1 = doc[1].get_text("text") if doc.page_count > 1 else ""
    full = p0 + "\n" + p1

    bib = {}

    m = re.search(r"\(12\)\s*(.+)", full)
    if m: bib["문서유형"] = m.group(1).strip()

    # 공개번호 or 등록번호
    m = re.search(r"\(11\)\s*(?:공개번호|등록번호)\s+(\S+)", full)
    if m: bib["공개번호"] = m.group(1)

    m = re.search(r"\(43\)\s*공개일자\s+(\S+)", full)
    if m: bib["공개일자"] = m.group(1)

    m = re.search(r"\(45\)\s*등록일자\s+(\S+)", full)
    if m: bib["등록일자"] = m.group(1)

    m = re.search(r"\(21\)\s*출원번호\s+(\S+)", full)
    if m: bib["출원번호"] = m.group(1)

    m = re.search(r"\(22\)\s*출원일자\s+(\S+)", full)
    if m: bib["출원일자"] = m.group(1)

    m = re.search(r"심사청구일자\s+(\S+)", full)
    if m: bib["심사청구일자"] = m.group(1).rstrip(".")

    # 국제특허분류
    m = re.search(r"\(51\)\s*국제특허분류\(Int\. Cl\.\)\s*\n([\s\S]+?)(?=\(52\)|\(21\))", full)
    if m:
        bib["국제특허분류"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # CPC특허분류 (1·2페이지 합산에서 추출)
    cpc_codes = re.findall(r"[A-Z]\d+[A-Z]\s+[\d/]+\s+\(\d{4}\.\d{2}\)", full)
    bib["CPC특허분류"] = [c.strip() for c in cpc_codes]

    # 발명의 명칭
    m = re.search(r"\(54\)\s*발명의 명칭\s+(.+?)(?=\(57\))", full, re.DOTALL)
    if m:
        bib["발명의명칭"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # 요약
    m = re.search(r"\(57\)\s*요\s*약\s*\n([\s\S]+?)(?=대\s*표\s*도|공개특허|등록특허)", full)
    if m:
        bib["요약"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # 출원인
    m = re.search(r"\(71\)\s*출원인\s*\n([\s\S]+?)(?=\(72\)|\(74\))", full)
    if m:
        bib["출원인"] = [l.strip() for l in m.group(1).strip().splitlines() if l.strip()]

    # 발명자
    m = re.search(r"\(72\)\s*발명자\s*\n([\s\S]+?)(?=\(74\)|\(71\)|전체 청구항)", full)
    if m:
        bib["발명자"] = [l.strip() for l in m.group(1).strip().splitlines() if l.strip()]

    # 대리인
    m = re.search(r"\(74\)\s*대리인\s*\n([\s\S]+?)(?=전체 청구항|\(54\))", full)
    if m:
        bib["대리인"] = [l.strip() for l in m.group(1).strip().splitlines() if l.strip()]

    # 청구항 수
    m = re.search(r"전체 청구항 수\s*:\s*총\s*(\d+)\s*항", full)
    if m: bib["청구항수"] = int(m.group(1))

    return bib


# ─────────────────────────────────────────────────────────────
# 청구범위
# ─────────────────────────────────────────────────────────────
def parse_claims(doc) -> list:
    """청구항 N → 내용 리스트"""
    claims = []
    current = None
    in_claims = False

    for pg in range(doc.page_count):
        done = False
        for item in get_lines(doc[pg]):
            if item["footer"]:
                continue
            t = item["text"]

            if re.match(r"^명\s*세\s*서$", t):
                continue
            if re.match(r"^청\s*구\s*범\s*위$", t):
                in_claims = True
                continue
            if re.match(r"^발\s*명\s*의\s*설\s*명$", t):
                if current:
                    current["내용"] = current["내용"].strip()
                    claims.append(current)
                    current = None
                return claims

            if not in_claims:
                continue

            m = re.match(r"^청구항\s+(\d+)\s*$", t)
            if m:
                if current:
                    current["내용"] = current["내용"].strip()
                    claims.append(current)
                current = {"청구항번호": int(m.group(1)), "내용": ""}
                continue

            if current is not None:
                current["내용"] += t + "\n"

    if current and current["내용"].strip():
        current["내용"] = current["내용"].strip()
        claims.append(current)
    return claims


# ─────────────────────────────────────────────────────────────
# 발명의 설명
# ─────────────────────────────────────────────────────────────
def parse_description(doc) -> list:
    """
    섹션 헤더(size≈10) + [NNNN] 단락번호 + 본문 구조 파싱.

    한국 특허 특이사항:
      [NNNN]이 단락 첫 줄의 오른쪽 컬럼에 배치되어,
      PyMuPDF 스트림상 "첫 줄 → [NNNN] → 나머지 줄" 순서로 추출됨.
      → hold-last-line 기법: 줄을 바로 커밋하지 않고 다음 토큰을 보고 결정.
        · 다음이 [NNNN] → 이 줄은 새 단락의 첫 줄
        · 다음이 일반 본문 / 헤더 → 이 줄은 현재 단락의 마지막 줄
    """
    sections    = []
    cur_sec     = None
    cur_para    = None
    buf         = []       # 첫 [NNNN] 이전에 쌓이는 본문 줄
    held_line   = None     # 아직 커밋 안 된 직전 줄
    in_desc     = False
    after_symb  = False    # 부호의 설명 이후 → 도면 영역 무시

    # ── 헬퍼 ──────────────────────────────────────────────────
    def commit_held():
        """held_line을 현재 para 또는 buf에 추가"""
        nonlocal held_line
        if held_line is None:
            return
        if cur_para is not None:
            cur_para["내용"] += held_line + "\n"
        elif cur_sec is not None:
            buf.append(held_line)
        held_line = None

    def flush_para():
        """cur_para를 cur_sec에 저장 (held_line은 건드리지 않음)"""
        nonlocal cur_para
        if cur_para is not None and cur_sec is not None:
            cur_para["내용"] = cur_para["내용"].strip()
            cur_sec["단락"].append(cur_para)
            cur_para = None

    def new_section(hdr_text):
        nonlocal cur_sec, buf
        commit_held()   # 직전 줄 → 현재 단락에 귀속
        flush_para()
        if buf and cur_sec is not None:
            cur_sec["단락"].append({"번호": None, "내용": "\n".join(buf).strip()})
        buf = []
        if cur_sec is not None:
            sections.append(cur_sec)
        cur_sec = {"header": hdr_text, "단락": []}

    # ── 메인 루프 ──────────────────────────────────────────────
    for pg in range(doc.page_count):
        for item in get_lines(doc[pg]):
            if item["footer"]:
                continue
            t = item["text"]

            if re.match(r"^발\s*명\s*의\s*설\s*명$", t):
                in_desc = True
                continue

            if not in_desc:
                continue

            # 섹션 헤더
            if item["header"]:
                if after_symb:
                    # 도면 영역 헤더 → 무시 (새 섹션 생성 않음)
                    continue
                new_section(t)
                # 부호의 설명 이후부터는 도면 영역으로 간주
                if re.sub(r"\s+", "", t) == "부호의설명":
                    after_symb = True
                continue

            # 단락번호 [NNNN]
            # held_line이 이 단락의 첫 줄 → prefix로 사용
            if item["para_num"]:
                prefix    = held_line       # 첫 줄 구제
                held_line = None
                flush_para()               # 이전 단락 저장 (held 없는 상태)
                cur_para = {
                    "번호": t,
                    "내용": (prefix + "\n") if prefix else "",
                }
                buf = []
                continue

            # 일반 본문 → 직전 held_line 커밋, 현재 줄 hold
            commit_held()
            held_line = t

    # ── 마지막 정리 ────────────────────────────────────────────
    commit_held()
    flush_para()
    if buf and cur_sec is not None:
        cur_sec["단락"].append({"번호": None, "내용": "\n".join(buf).strip()})
    if cur_sec is not None:
        sections.append(cur_sec)

    for sec in sections:
        for para in sec["단락"]:
            para["내용"] = para["내용"].strip()

    return sections


# ─────────────────────────────────────────────────────────────
# 부호 설명 (발명의설명 섹션에서 추출)
# ─────────────────────────────────────────────────────────────
def extract_symbol_legend(description_sections: list) -> list:
    """발명의설명 내 '부호의 설명' 섹션 내용을 줄 단위 리스트로 반환"""
    for sec in description_sections:
        if re.sub(r"\s+", "", sec["header"]) == "부호의설명":
            all_lines = []
            for para in sec["단락"]:
                all_lines.extend(para["내용"].splitlines())
            return [l.strip() for l in all_lines if l.strip()]
    return []


# ─────────────────────────────────────────────────────────────
# 도면 페이지 목록
# ─────────────────────────────────────────────────────────────
def list_drawing_pages(doc) -> list:
    pages = []
    for pg in range(doc.page_count):
        text = doc[pg].get_text("text").strip()
        # 노이즈 제거 후 "도면N" 레이블만 남는지 확인
        cleaned = re.sub(r"공개특허\s*\S+|등록특허\s*\S+|-\s*\d+\s*-", "", text).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        # "도면3 도면4" 또는 "도면3" 형태
        if re.match(r"^(도면\d+\s*)+$", cleaned):
            pages.append(pg + 1)
    return pages


# ─────────────────────────────────────────────────────────────
# 메인 파싱
# ─────────────────────────────────────────────────────────────
def parse_patent(pdf_path: Path) -> dict:
    doc = fitz.open(pdf_path)
    desc = parse_description(doc)
    result = {
        "파일명": pdf_path.name,
        "서지사항":   extract_biblio(doc),
        "청구범위":   parse_claims(doc),
        "발명의설명": desc,
        "부호설명":   extract_symbol_legend(desc),
        "도면페이지": list_drawing_pages(doc),
    }
    doc.close()
    return result


# ─────────────────────────────────────────────────────────────
# 출력 / 저장
# ─────────────────────────────────────────────────────────────
def process(pdf_path: Path):
    stem   = pdf_path.stem
    result = parse_patent(pdf_path)

    out = OUTPUT_DIR / f"{stem}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ── 콘솔 요약 ──
    bib = result["서지사항"]
    print(f"\n{'='*60}")
    print(f" {stem}")
    print(f"{'='*60}")
    print("[서지사항]")
    for k, v in bib.items():
        disp = json.dumps(v, ensure_ascii=False)
        print(f"  {k}: {disp[:90]}")

    claims = result["청구범위"]
    print(f"\n[청구범위] 총 {len(claims)}개")
    for c in claims[:3]:
        preview = c["내용"][:60].replace("\n", " ")
        print(f"  청구항{c['청구항번호']}: {preview}...")
    if len(claims) > 3:
        print(f"  ... (이하 {len(claims)-3}개 생략)")

    desc = result["발명의설명"]
    total_para = sum(len(s["단락"]) for s in desc)
    print(f"\n[발명의설명] 섹션 {len(desc)}개 / 단락 {total_para}개")
    for s in desc:
        print(f"  [{s['header']}] {len(s['단락'])}단락")

    print(f"\n[부호설명] {len(result['부호설명'])}줄")
    print(f"[도면페이지] {result['도면페이지']}")
    print(f"\n저장 → {out}\n")
    return result


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    patent_dir = Path("사용한 특허")
    pdfs = sorted(patent_dir.glob("*.pdf"))
    if not pdfs:
        print("PDF 파일 없음")
        sys.exit(1)
    for p in pdfs:
        process(p)
