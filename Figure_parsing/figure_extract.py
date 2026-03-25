"""
figure_extract.py - 특허 PDF → 도면 이미지 추출

구조:
  Figure_parsing/사용한 특허/*.pdf
  → Figure_parsing/output/<출원번호>/도면1.png, 도면2.png, ...

사용법:
  python figure_extract.py <특허.pdf>   -- 단일 파일
  python figure_extract.py              -- 사용한 특허/ 전체 일괄
"""

import re
import sys
from pathlib import Path

import fitz  # PyMuPDF


def _get_figure_labels(page) -> list[tuple[float, int]]:
    """
    페이지에서 '도면N' 레이블 추출.
    Returns: [(label_y, fig_num), ...] y좌표 오름차순 정렬
    """
    labels = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = block
        for line in text.split("\n"):
            m = re.fullmatch(r"도면(\d+)", line.strip())
            if m:
                labels.append((y0, int(m.group(1))))
    labels.sort(key=lambda x: x[0])
    return labels


def _get_images_with_pos(page, doc) -> list[tuple[float, int]]:
    """
    페이지 이미지의 (y좌표, xref) 리스트, y오름차순 정렬.
    """
    result = []
    for img in page.get_images(full=True):
        xref = img[0]
        rects = page.get_image_rects(xref)
        if rects:
            y = rects[0].y0
            result.append((y, xref))
    result.sort(key=lambda x: x[0])
    return result


def extract_figures(pdf_path: Path, out_dir: Path) -> list[Path]:
    """
    PDF에서 도면 이미지 추출 → out_dir/도면N.<ext> 저장
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

        imgs = _get_images_with_pos(page, doc)
        if not imgs:
            continue

        # 레이블-이미지 매핑: 레이블 아래 가장 가까운 이미지
        used = set()
        for label_y, fig_num in labels:
            best_idx = None
            best_dist = float("inf")
            for i, (img_y, xref) in enumerate(imgs):
                if i in used:
                    continue
                if img_y > label_y:
                    dist = img_y - label_y
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i

            if best_idx is None:
                print(f"  경고: 도면{fig_num} 매핑 이미지 없음 (페이지{page_idx+1})")
                continue

            used.add(best_idx)
            _, xref = imgs[best_idx]

            base_img = doc.extract_image(xref)
            img_bytes = base_img["image"]
            ext = base_img["ext"]

            out_path = out_dir / f"도면{fig_num}.{ext}"
            out_path.write_bytes(img_bytes)
            saved.append(out_path)
            print(f"  저장: {out_path.name}")

    return saved


if __name__ == "__main__":
    BASE = Path(__file__).parent
    OUT = BASE / "output"

    if len(sys.argv) >= 2:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted((BASE / "사용한 특허").glob("*.pdf"))

    for pdf_path in targets:
        print(f"\n처리 중: {pdf_path.name}")
        out_dir = OUT / pdf_path.stem
        files = extract_figures(pdf_path, out_dir)
        print(f"  → 총 {len(files)}개 도면 저장")
