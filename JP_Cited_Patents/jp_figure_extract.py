"""
jp_figure_extract.py - 일본 특허 PDF → 도면 이미지 추출

구조:
  JP_Cited_Patents/사용한 일본인용문헌/*.pdf
  → JP_Cited_Patents/output/<파일명>/図N.png ...

매핑 방식:
  각 페이지에서 【図N】 스탠드얼론 레이블의 (x, y) 좌표를 추출하고
  레이블 바로 아래 같은 컬럼의 이미지와 1:1 매핑.

  ※ 스탠드얼론 레이블: 【図N】 만 있는 라인 (뒤에 설명문 없는 것)
     → 발명의설명 내 「【図１】説明文...」 형태는 제외됨

사용법:
  python jp_figure_extract.py <특허.pdf>   -- 단일 파일
  python jp_figure_extract.py              -- 사용한 일본인용문헌/ 전체 일괄
"""

import re
import sys
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

# Windows cp949 콘솔에서 일본어 문자 출력 가능하도록 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def nfkc(s: str) -> str:
    """전각 숫자 → 반각 정규화 (図１ → 図1)"""
    return unicodedata.normalize('NFKC', s)


def _get_figure_labels(page) -> list[tuple[float, float, int]]:
    """
    스탠드얼론 【図N】 레이블 위치 추출.
    Returns: [(label_x, label_y, fig_num), ...] y → x 오름차순
    """
    labels = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            text = ''.join(s['text'] for s in line['spans']).strip()
            # 정확히 【図N】 형태만 (설명문 붙은 것 제외)
            m = re.fullmatch(r'【図([０-９\d]+)】', text)
            if m:
                x0, y0 = line['bbox'][0], line['bbox'][1]
                fig_num = int(nfkc(m.group(1)))
                labels.append((x0, y0, fig_num))
    labels.sort(key=lambda v: (v[1], v[0]))
    return labels


def _get_images_with_pos(page) -> list[tuple[float, float, int]]:
    """
    페이지 이미지 (x, y, xref) 리스트, y → x 오름차순
    """
    result = []
    for img in page.get_images(full=True):
        xref  = img[0]
        rects = page.get_image_rects(xref)
        if rects:
            result.append((rects[0].x0, rects[0].y0, xref))
    result.sort(key=lambda v: (v[1], v[0]))
    return result


def extract_jp_figures(pdf_path: Path, out_dir: Path) -> list[Path]:
    """
    PDF에서 일본 도면 이미지 추출 → out_dir/図N.<ext> 저장
    Returns: 저장된 파일 경로 리스트
    """
    doc = fitz.open(str(pdf_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]

        if not page.get_images():
            continue

        labels = _get_figure_labels(page)
        if not labels:
            continue

        imgs = _get_images_with_pos(page)
        if not imgs:
            continue

        # 레이블-이미지 위치 매핑
        # 조건: 이미지가 레이블 아래 + 같은 컬럼(x 차이 ≤ 80pt)
        used = set()
        for label_x, label_y, fig_num in labels:
            best_idx  = None
            best_dist = float('inf')

            for i, (img_x, img_y, _) in enumerate(imgs):
                if i in used:
                    continue
                if img_y < label_y - 5:       # 레이블보다 위는 제외
                    continue
                if abs(img_x - label_x) > 80:  # 다른 컬럼 제외
                    continue
                dist = (img_y - label_y) ** 2 + (img_x - label_x) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_idx  = i

            if best_idx is None:
                print(f'  경고: 図{fig_num} 매핑 이미지 없음 (페이지{page_idx + 1})')
                continue

            used.add(best_idx)
            _, _, xref = imgs[best_idx]

            base_img  = doc.extract_image(xref)
            img_bytes = base_img['image']
            ext       = base_img['ext']

            out_path = out_dir / f'図{fig_num}.{ext}'
            out_path.write_bytes(img_bytes)
            saved.append(out_path)
            print(f'  저장: {out_path.name}')

    return saved


if __name__ == '__main__':
    BASE = Path(__file__).parent
    OUT  = BASE / 'output'

    if len(sys.argv) >= 2:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted((BASE / '사용한 일본인용문헌').glob('*.pdf'))

    for pdf_path in targets:
        print(f'\n처리 중: {pdf_path.name}')
        out_dir = OUT / pdf_path.stem
        files   = extract_jp_figures(pdf_path, out_dir)
        print(f'  → 총 {len(files)}개 도면 저장')
