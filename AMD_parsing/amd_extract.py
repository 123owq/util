"""
amd_extract.py - 보정서 PDF → JSON 파싱

구조:
  meta      : 출원번호, 출원인, 대리인, 보정구분, 발송번호
  수수료    : 보정료, 합계
  보정목록  : [{ 보정대상항목, 보정방법, 보정내용 }, ...]

사용법:
  python amd_extract.py <보정서.pdf>            -- 단일 파일
  python amd_extract.py                         -- 사용한 보정서/ 전체 일괄
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF


def _normalize_field_names(text: str) -> str:
    """【필드명\n계속】 형태의 줄바꿈 정규화 → 【필드명계속】"""
    return re.sub(
        r'【([^】\n]{1,30})\n([^】\n]{1,30})】',
        lambda m: '【' + m.group(1).rstrip() + m.group(2).lstrip() + '】',
        text
    )


def _get_field(text: str, key: str) -> str | None:
    """【키】 바로 다음 줄의 값 추출"""
    m = re.search(r'【' + re.escape(key) + r'】\s*\n([^\n【]+)', text)
    return m.group(1).strip() if m else None


def parse_amd(pdf_path: str | Path) -> dict:
    """보정서 PDF → 구조화 dict"""
    doc = fitz.open(str(pdf_path))

    # 전 페이지 텍스트 합치기 (페이지 경계 무시)
    full_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))

    # 필드명 줄바꿈 정규화
    full_text = _normalize_field_names(full_text)

    # ── 1. 메타 ──────────────────────────────────────────────────────────────
    meta = {
        "출원번호":  _get_field(full_text, "출원번호"),
        "보정구분":  _get_field(full_text, "보정구분"),
        "제출처":    _get_field(full_text, "제출처"),
        "발송번호":  _get_field(full_text, "제출원인이 된 서류의 발송번호"),
        "출원인":    None,
        "대리인":    None,
    }

    # 출원인: 【제출인】 ~ 【사건의 표시】 사이의 【명칭】
    m = re.search(r'【제출인】(.*?)【사건의 표시】', full_text, re.DOTALL)
    if m:
        nm = re.search(r'【명칭】\s*\n([^\n【]+)', m.group(1))
        if nm:
            meta["출원인"] = nm.group(1).strip()

    # 대리인: 【대리인】 ~ (【사건의 표시】|【취지】) 사이의 【성명】 or 【명칭】
    m = re.search(r'【대리인】(.*?)(?:【사건의 표시】|【취지】)', full_text, re.DOTALL)
    if m:
        nm = re.search(r'【(?:성명|명칭)】\s*\n([^\n【]+)', m.group(1))
        if nm:
            meta["대리인"] = nm.group(1).strip()

    # ── 2. 수수료 ────────────────────────────────────────────────────────────
    수수료 = {
        "보정료": _get_field(full_text, "보정료"),
        "합계":   _get_field(full_text, "합계"),
    }

    # ── 3. 보정목록 ──────────────────────────────────────────────────────────
    보정목록 = []

    # 【보정대상항목】 단위로 분리
    parts = re.split(r'【보정대상항목】\s*\n', full_text)

    for part in parts[1:]:
        lines = part.lstrip('\n').split('\n')
        항목 = lines[0].strip()

        # 표지의 "별지와 같음" 플레이스홀더 스킵
        if '별지' in 항목:
            continue

        # 보정방법
        m_method = re.search(r'【보정방법】\s*\n([^\n【]+)', part)
        방법 = m_method.group(1).strip() if m_method else None

        # 보정내용 (삭제는 내용 없음)
        내용 = None
        if 방법 != '삭제':
            m_content = re.search(
                r'【보정내용】\s*\n(.*?)(?=\n【보정대상항목】|\Z)',
                part, re.DOTALL
            )
            if m_content:
                content_text = m_content.group(1).strip()
                # 【청구항 X】 헤더 제거 (보정내용 첫 줄)
                content_text = re.sub(r'^【[^】]+】\s*\n', '', content_text).strip()
                # 연속 빈 줄 정리
                content_text = re.sub(r'\n{3,}', '\n\n', content_text)
                내용 = content_text if content_text else None

        보정목록.append({
            "보정대상항목": 항목,
            "보정방법":     방법,
            "보정내용":     내용,
        })

    return {
        "meta":    meta,
        "수수료":  수수료,
        "보정목록": 보정목록,
    }


if __name__ == "__main__":
    BASE = Path(__file__).parent
    OUT  = BASE / "output"
    OUT.mkdir(exist_ok=True)

    if len(sys.argv) >= 2:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted((BASE / "사용한 보정서").glob("*.pdf"))

    for pdf_path in targets:
        print(f"파싱 중: {pdf_path.name}")
        result = parse_amd(pdf_path)
        out_path = OUT / (pdf_path.stem + ".json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  → {out_path}")
