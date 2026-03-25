"""
pipeline.py - kipris/output/ 순회하며 PDF 파싱
- 01_특허/patent.pdf        → patent_extract.parse_patent()  → 01_특허/patent_parsed.json
- 02_의견제출통지서/oa_*.pdf → extract_v6.parse_oa()          → 02_의견제출통지서/oa_*_parsed.json
- 01_특허/patent.pdf        → figure_extract.extract_figures() → 05_도면/도면N.png

실행: pdf_ex/ 폴더에서 python pipeline.py
"""

import importlib.util             # 파일 경로로 직접 모듈 로드 (sys.path 조작 불필요)
import json                       # JSON 저장용
import logging                    # 로그 출력용
from pathlib import Path          # 파일/폴더 경로 다루기 (문자열보다 편함)

# 이 파일(pipeline.py)이 있는 폴더 = pdf_ex/ 의 절대경로
_ROOT = Path(__file__).parent


def _load_module(name: str, file_path: Path):
    """파일 경로로 직접 모듈 로드 (패키지 구조 없이도 동작)"""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_patent = _load_module("patent_extract", _ROOT / "patent_parsing" / "patent_extract.py")
_oa     = _load_module("extract_v6",     _ROOT / "OA_parsing"     / "extract_v6.py")
_fig    = _load_module("figure_extract", _ROOT / "Figure_parsing"  / "figure_extract.py")

parse_patent      = _patent.parse_patent
parse_oa          = _oa.parse_oa
extract_tables    = _oa.extract_tables
get_table_bboxes  = _oa.get_table_bboxes
extract_figures   = _fig.extract_figures

import fitz  # PyMuPDF: parse_oa 호출 시 doc 객체 생성용

OUTPUT_BASE = _ROOT / "kipris_api" / "output"  # kipris/output/ 폴더 경로 (다운로드 결과가 여기 있음)

# 로그 설정: 터미널에만 출력 (파이프라인은 별도 로그 파일 안 만듦)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("PIPELINE")


def save_json(data: dict, path: Path):
    """dict를 JSON 파일로 저장"""
    path.write_text(                              # 파일에 텍스트 쓰기
        json.dumps(data, ensure_ascii=False, indent=2),  # 한글 유지, 들여쓰기 2칸
        encoding="utf-8"                          # UTF-8 인코딩
    )


def parse_patent_pdf(patent_dir: Path):
    """01_특허/patent.pdf 파싱 → patent_parsed.json 저장 (이미 있으면 스킵)"""
    pdf = patent_dir / "01_특허" / "patent.pdf"           # 특허 PDF 경로
    out = patent_dir / "01_특허" / "patent_parsed.json"   # 파싱 결과 저장 경로

    if not pdf.exists():          # PDF가 없으면 (다운로드 실패 등) 건너뜀
        return
    if out.exists():              # 이미 파싱 결과가 있으면 재파싱 안 함
        log.info("    특허 파싱 스킵 (이미 존재)")
    else:
        try:
            result = parse_patent(pdf)    # 특허 PDF → dict (서지사항, 청구범위, 발명설명 등)
            save_json(result, out)        # 결과를 JSON으로 저장
            log.info(f"    특허 파싱 완료 → patent_parsed.json")
        except Exception as e:
            log.warning(f"    특허 파싱 실패: {e}")  # 실패해도 전체 중단 없이 계속 진행

    extract_patent_figures(pdf, patent_dir)  # 도면 추출 (항상 실행)


def extract_patent_figures(pdf: Path, patent_dir: Path):
    """01_특허/patent.pdf → 05_도면/도면N.<ext> 추출 (이미 있으면 스킵)"""
    if not pdf.exists():
        return

    fig_dir = patent_dir / "05_도면"

    # 이미 추출된 경우 스킵
    if fig_dir.exists() and any(fig_dir.iterdir()):
        log.info("    도면 추출 스킵 (이미 존재)")
        return

    try:
        saved = extract_figures(pdf, fig_dir)  # 도면N.<ext> 저장
        if saved:
            log.info(f"    도면 추출 완료 → 05_도면/ ({len(saved)}개)")
        else:
            log.info("    도면 없음 (도면 섹션 미발견)")
    except Exception as e:
        log.warning(f"    도면 추출 실패: {e}")


def parse_oa_pdfs(patent_dir: Path):
    """02_의견제출통지서/oa_*.pdf 전체 파싱 → oa_*_parsed.json 저장 (이미 있으면 스킵)"""
    oa_dir = patent_dir / "02_의견제출통지서"  # 의견제출통지서 폴더
    if not oa_dir.exists():                    # 의견제출통지서가 없는 특허면 건너뜀
        return

    for pdf in sorted(oa_dir.glob("oa_*.pdf")):                   # oa_로 시작하는 PDF 전체 순회
        out = pdf.with_name(pdf.stem + "_parsed.json")             # 예: oa_952013047194487_parsed.json

        if out.exists():                                            # 이미 파싱된 파일은 스킵
            log.info(f"    OA 파싱 스킵: {pdf.name}")
            continue

        try:
            doc            = fitz.open(pdf)              # PyMuPDF로 PDF 열기
            tables_by_page = extract_tables(pdf)         # 페이지별 표 추출 (거절이유 표 등)
            table_bboxes   = get_table_bboxes(pdf)       # 표 위치 정보 (본문과 표 영역 구분용)
            result         = parse_oa(doc, tables_by_page, table_bboxes)  # 의견제출통지서 파싱 → dict
            doc.close()                                  # PDF 파일 닫기
            save_json(result, out)                       # 결과 저장
            log.info(f"    OA 파싱 완료: {pdf.name} → {out.name}")
        except Exception as e:
            log.warning(f"    OA 파싱 실패 ({pdf.name}): {e}")  # 실패해도 다음 파일 계속 진행


def main():
    # kipris/output/ 안의 폴더 목록 (각 폴더 = 특허 1건)
    patent_dirs = sorted(d for d in OUTPUT_BASE.iterdir() if d.is_dir())

    log.info("=" * 60)
    log.info(f"파이프라인 시작 | 총 {len(patent_dirs)}건")
    log.info("=" * 60)

    for i, patent_dir in enumerate(patent_dirs):
        log.info(f"\n[{i+1}/{len(patent_dirs)}] {patent_dir.name}")
        parse_patent_pdf(patent_dir)   # 특허 PDF 파싱
        parse_oa_pdfs(patent_dir)      # 의견제출통지서 PDF 파싱

    log.info("\n" + "=" * 60)
    log.info("파이프라인 완료")
    log.info("=" * 60)


if __name__ == "__main__":
    main()   # python pipeline.py 로 직접 실행할 때만 동작
