"""
jp_extract.py - 일본 특허 공개공보 PDF → JSON 변환기 (정보손실 0%)

구조:
  공보번호          : JP YYYY-NNNNNN A  (푸터에서 추출)
  요약              : (57)【要約】 → 【課題】, 【解決手段】
  특허청구범위      : 【請求項N】
  발명의상세한설명  : 섹션 헤더(【XX】) + 【NNNN】 단락번호 + 본문
  인용문헌          : 【特許文献N】, 【非特許文献N】

사용법:
  python jp_extract.py <특허.pdf>   -- 단일 파일
  python jp_extract.py              -- 사용한 일본인용문헌/ 전체 일괄
"""

import sys
import json
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

# Windows cp949 콘솔에서 일본어 문자 출력 가능하도록 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def nfkc(s: str) -> str:
    """전각 숫자·알파벳 → 반각 정규화"""
    return unicodedata.normalize('NFKC', s)


# ─────────────────────────────────────────────────────────────
# 노이즈 판정
# ─────────────────────────────────────────────────────────────
def is_footer(font: str) -> bool:
    """GothicBBB-Medium → 페이지번호 / 공보번호 반복 푸터"""
    return 'GothicBBB' in font


def is_line_number(text: str) -> bool:
    """10, 20, 30, 40, 50 → 일본 특허 우측 여백 줄번호 노이즈"""
    return bool(re.match(r'^\d+$', text)) and int(text) % 10 == 0 and 0 < int(text) <= 50


# ─────────────────────────────────────────────────────────────
# 페이지 → 구조화 라인 목록
# ─────────────────────────────────────────────────────────────
def get_lines(page) -> list[dict]:
    """
    반환: [{ text, is_para_num, is_footer }]
    is_para_num : 【NNNN】 (전각 4자리 숫자) → 단락번호
    is_footer   : GothicBBB 폰트 or 줄번호 노이즈
    """
    result = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            spans = line['spans']
            if not spans:
                continue
            text = ''.join(s['text'] for s in spans).strip()
            if not text:
                continue
            font = spans[0]['font']

            footer   = is_footer(font) or is_line_number(text)
            is_pnum  = bool(re.fullmatch(r'【[０-９]{4}】', text))

            result.append({
                'text':        text,
                'is_para_num': is_pnum,
                'is_footer':   footer,
            })
    return result


# ─────────────────────────────────────────────────────────────
# 공보번호 추출
# ─────────────────────────────────────────────────────────────
def extract_pub_number(doc) -> dict:
    """
    GothicBBB 푸터에서 'JP YYYY-NNNNNN A YYYY.M.DD' 추출.
    일부 PDF는 첫 줄에 공보번호 표기.
    """
    for pg in doc:
        text = pg.get_text()
        m = re.search(r'(JP\s+\d{4}-\d+\s+[A-Z]\d*)\s+([\d.]+)', text)
        if m:
            return {'공보번호': m.group(1).strip(), '공개일': m.group(2).strip()}
    return {'공보번호': None, '공개일': None}


# ─────────────────────────────────────────────────────────────
# 요약 (抄録)
# ─────────────────────────────────────────────────────────────
def extract_abstract(doc) -> dict:
    """
    (57)【要約】 섹션 → 【課題】, 【解決手段】, 【選択図】 추출.
    텍스트 분할 방식으로 첫 2페이지에서 추출.
    """
    full = '\n'.join(doc[i].get_text() for i in range(min(2, doc.page_count)))

    # (57)【要約】 이후 ~ 【特許請求の範囲】 이전
    m = re.search(r'\(57\)【要約】.*?\n([\s\S]+?)(?=【特許請求の範囲】)', full)
    if not m:
        return {}
    body = m.group(1)

    abstract = {}

    m2 = re.search(r'【課題】([\s\S]+?)(?=【解決手段】|【選択図】|$)', body)
    if m2:
        abstract['과제'] = re.sub(r'\s+', ' ', m2.group(1)).strip()

    m3 = re.search(r'【解決手段】([\s\S]+?)(?=【選択図】|$)', body)
    if m3:
        abstract['해결수단'] = re.sub(r'\s+', ' ', m3.group(1)).strip()

    m4 = re.search(r'【選択図】\s*(.+)', body)
    if m4:
        abstract['선택도'] = m4.group(1).strip()

    return abstract


# ─────────────────────────────────────────────────────────────
# 특허청구범위
# ─────────────────────────────────────────────────────────────
def parse_claims(doc) -> list[dict]:
    """【請求項N】 단위로 청구항 파싱"""
    claims   = []
    current  = None
    in_claims = False

    for pg in range(doc.page_count):
        for item in get_lines(doc[pg]):
            if item['is_footer']:
                continue
            t = item['text']

            if t == '【特許請求の範囲】':
                in_claims = True
                continue
            if t == '【発明の詳細な説明】':
                if current:
                    current['내용'] = current['내용'].strip()
                    claims.append(current)
                    current = None
                return claims

            if not in_claims:
                continue

            # 전각·반각 숫자 모두 지원
            m = re.fullmatch(r'【請求項([０-９\d]+)】', t)
            if m:
                if current:
                    current['내용'] = current['내용'].strip()
                    claims.append(current)
                current = {'청구항번호': int(nfkc(m.group(1))), '내용': ''}
                continue

            if current is not None:
                current['내용'] += t + '\n'

    if current and current['내용'].strip():
        current['내용'] = current['내용'].strip()
        claims.append(current)
    return claims


# ─────────────────────────────────────────────────────────────
# 발명의 상세한 설명
# ─────────────────────────────────────────────────────────────
_KNOWN_SECTIONS = {
    '【技術分野】', '【背景技術】', '【発明の開示】',
    '【発明が解決しようとする課題】', '【課題を解決するための手段】',
    '【発明の効果】', '【発明を実施するための最良の形態】',
    '【実施の形態】', '【実施例】', '【図面の簡単な説明】',
    '【符号の説明】', '【産業上の利用分野】',
}


def _is_section_header(text: str) -> bool:
    if text in _KNOWN_SECTIONS:
        return True
    # 2~20자 단독 【...】 라인이면서 단락번호·청구항·도면 레이블이 아닌 것
    if re.fullmatch(r'【[^】]{2,20}】', text):
        if not re.fullmatch(r'【[０-９]{4}】', text):   # 단락번호 제외
            if not re.match(r'^【請求項', text):          # 청구항 제외
                if not re.match(r'^【図[０-９\d]', text):  # 도면 레이블 제외
                    return True
    return False


def parse_description(doc) -> list[dict]:
    """
    발명의 상세한 설명 → [{ 섹션: str, 단락: [{ 번호: str|None, 내용: str }] }]
    인용문헌(【特許文献N】 등)은 단락 내용으로 포함됨.
    """
    sections  = []
    cur_sec   = None
    cur_para  = None
    in_desc   = False

    def flush_para():
        nonlocal cur_para
        if cur_para and cur_sec is not None:
            cur_para['내용'] = cur_para['내용'].strip()
            if cur_para['내용']:
                cur_sec['단락'].append(cur_para)
            cur_para = None

    def new_section(hdr: str):
        nonlocal cur_sec
        flush_para()
        if cur_sec is not None:
            sections.append(cur_sec)
        cur_sec = {'섹션': hdr, '단락': []}

    for pg in range(doc.page_count):
        for item in get_lines(doc[pg]):
            if item['is_footer']:
                continue
            t = item['text']

            if t == '【発明の詳細な説明】':
                in_desc = True
                continue
            if not in_desc:
                continue

            # 요약의계속・프론트페이지계속 → 발명설명 종료 (말미 부가 페이지)
            if t in ('【要約の続き】', 'フロントページの続き'):
                flush_para()
                if cur_sec is not None:
                    sections.append(cur_sec)
                    cur_sec = None
                in_desc = False
                continue

            if _is_section_header(t):
                new_section(t)
                continue

            if item['is_para_num']:
                flush_para()
                cur_para = {'번호': t, '내용': ''}
                continue

            # 인용문헌 라인 (단락번호 없이 단독 등장하는 경우)
            if re.match(r'^【(?:特許|非特許)文献[０-９\d]+】', t):
                if cur_para is None and cur_sec is not None:
                    cur_para = {'번호': None, '내용': ''}
                if cur_para is not None:
                    cur_para['내용'] += t + '\n'
                continue

            # 일반 본문
            if cur_para is not None:
                cur_para['내용'] += t + '\n'
            elif cur_sec is not None:
                cur_para = {'번호': None, '내용': t + '\n'}

    flush_para()
    if cur_sec is not None:
        sections.append(cur_sec)

    for sec in sections:
        for para in sec['단락']:
            para['내용'] = para['내용'].strip()

    return sections


# ─────────────────────────────────────────────────────────────
# 인용문헌 목록 (발명의설명에서 분리 추출)
# ─────────────────────────────────────────────────────────────
def extract_cited_refs(description: list[dict]) -> list[dict]:
    """발명의상세한설명 내 【特許文献N】, 【非特許文献N】 줄 추출"""
    refs = []
    for sec in description:
        for para in sec['단락']:
            for line in para['내용'].splitlines():
                m = re.match(r'^(【(?:特許|非特許)文献[０-９\d]+】)\s*(.+)', line.strip())
                if m:
                    refs.append({'번호': m.group(1), '내용': m.group(2).strip()})
    return refs


# ─────────────────────────────────────────────────────────────
# 메인 파싱
# ─────────────────────────────────────────────────────────────
def parse_jp_patent(pdf_path: Path) -> dict:
    doc  = fitz.open(str(pdf_path))
    pub  = extract_pub_number(doc)
    desc = parse_description(doc)

    result = {
        '파일명':           pdf_path.name,
        '공보번호':         pub['공보번호'],
        '공개일':           pub['공개일'],
        '요약':             extract_abstract(doc),
        '특허청구범위':     parse_claims(doc),
        '발명의상세한설명': desc,
        '인용문헌':         extract_cited_refs(desc),
    }
    doc.close()
    return result


# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    BASE = Path(__file__).parent
    OUT  = BASE / 'output'
    OUT.mkdir(exist_ok=True)

    if len(sys.argv) >= 2:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted((BASE / '사용한 일본인용문헌').glob('*.pdf'))

    for pdf_path in targets:
        print(f'\n파싱 중: {pdf_path.name}')
        result    = parse_jp_patent(pdf_path)
        out_path  = OUT / (pdf_path.stem + '.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f'  공보번호: {result["공보번호"]}  공개일: {result["공개일"]}')
        print(f'  요약 항목: {list(result["요약"].keys())}')
        print(f'  청구항: {len(result["특허청구범위"])}개')
        para_count = sum(len(s["단락"]) for s in result["발명의상세한설명"])
        print(f'  발명의설명: 섹션 {len(result["발명의상세한설명"])}개 / 단락 {para_count}개')
        print(f'  인용문헌: {len(result["인용문헌"])}건')
        print(f'  → {out_path}')
