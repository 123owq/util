"""
JP_tool2.py - 일본 특허 청구항 구성요소 파싱 + 발명설명 단락 매핑

구조 원칙:
  코드  → 확정적 처리 (독립항/종속항 구분, 인용 항번호 추출)
  LLM   → 의미 분석 (구성요소 추출, 단락 매핑)

입력: JP_Cited_Patents/output/*.json  (jp_extract.py 출력)
출력: JP_Cited_Patents/output/jp_tool2_<stem>.json

사용법:
  python JP_tool2.py <jp_json파일> [청구항번호,...]
  python JP_tool2.py JP_Cited_Patents/output/JP200600150602A0.json
  python JP_tool2.py JP_Cited_Patents/output/JP200600150602A0.json 1,2
"""

import json
import re
import os
import sys
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
MODEL = "deepseek/deepseek-chat-v3.1"


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def nfkc(s: str) -> str:
    return unicodedata.normalize('NFKC', s)


def normalize_para_num(num: str) -> str:
    """【０００１】 → [0001]  (LLM 프롬프트 가독성용)"""
    if num and re.fullmatch(r'【[０-９\d]{4}】', num):
        return f'[{nfkc(num[1:-1])}]'
    return num


# ─────────────────────────────────────────────────────────────
# 청구항 구조 파싱 (독립항 / 종속항)
# ─────────────────────────────────────────────────────────────
_DEP_PATTERNS = [
    # 請求項X〜Y のいずれか(一項)? に?記載の
    (r'請求項\s*([０-９\d]+)\s*[〜～]\s*([０-９\d]+)[^\u8a18]*?記載の', 'range'),
    # 請求項X、Y(、Z…) のいずれか? に?記載の
    (r'請求項\s*([０-９\d]+(?:[、，,]\s*[０-９\d]+)+)\s*(?:のいずれか(?:一項)?)?\s*に?記載の', 'list'),
    # 請求項X 又は/または/或いは/もしくは Y に?記載の
    (r'請求項\s*([０-９\d]+)\s*(?:又は|或いは|または|もしくは)\s*(?:請求項\s*)?([０-９\d]+)(?:のいずれか(?:一項)?)?\s*に?\s*記\s*載\s*の', 'two'),
    # 請求項X に記載の  (단독)
    (r'請求項\s*([０-９\d]+)\s*に\s*記\s*載\s*の', 'single'),
    # 請求項X 記載の  (「に」생략형)
    (r'請求項\s*([０-９\d]+)\s*記載の', 'single'),
]


def _parse_claim_structure(claims: list[dict]) -> list[dict]:
    """코드로 청구항 구조 파싱 (독립항/종속항 구분, 인용 항번호 추출)"""
    parsed = []
    for claim in claims:
        num  = claim['청구항번호']
        text = claim['내용']

        parents    = []
        claim_type = '독립항'

        for pattern, kind in _DEP_PATTERNS:
            m = re.search(pattern, text)
            if not m:
                continue
            if kind == 'range':
                s, e = int(nfkc(m.group(1))), int(nfkc(m.group(2)))
                parents = list(range(s, e + 1))
            elif kind == 'list':
                parents = [int(nfkc(x.strip())) for x in re.split(r'[、，,]', m.group(1)) if x.strip()]
            elif kind == 'two':
                parents = [int(nfkc(m.group(1))), int(nfkc(m.group(2)))]
            else:
                parents = [int(nfkc(m.group(1)))]
            claim_type = '종속항'
            break

        parsed.append({
            '청구항번호': num,
            '유형':       claim_type,
            '인용항':     parents,
            '본문':       text,
        })
    return parsed


# ─────────────────────────────────────────────────────────────
# 발명설명 단락 인덱스
# ─────────────────────────────────────────────────────────────
def _build_description_index(description: list[dict]) -> dict[str, str]:
    """발명의상세한설명 → { '[0001]': '내용...', ... }"""
    index = {}
    for section in description:
        for para in section.get('단락', []):
            raw_num = para.get('번호', '')
            content = para.get('내용', '')
            if raw_num:
                index[normalize_para_num(raw_num)] = content[:300]
    return index


# ─────────────────────────────────────────────────────────────
# 메인 분석 함수
# ─────────────────────────────────────────────────────────────
def jp_tool2(patent_json: dict, target_claim_nums: list[int] = None) -> dict:
    """
    일본 특허 JSON → 청구항 구성요소 파싱 + 발명설명 단락 매핑

    target_claim_nums: None이면 독립항만, 지정하면 해당 항만 처리
    """
    claims      = patent_json.get('특허청구범위', [])
    description = patent_json.get('발명의상세한설명', [])
    pub_num     = patent_json.get('공보번호', '')
    abstract    = patent_json.get('요약', {})

    title = abstract.get('과제', '')[:60] if abstract.get('과제') else pub_num

    parsed_claims = _parse_claim_structure(claims)

    if target_claim_nums is not None:
        target_claims = [c for c in parsed_claims if c['청구항번호'] in target_claim_nums]
    else:
        target_claims = [c for c in parsed_claims if c['유형'] == '독립항']

    para_index     = _build_description_index(description)
    para_list_text = '\n'.join(
        f'{num}: {content[:150]}...'
        for num, content in list(para_index.items())[:80]
    )

    system = """あなたは特許明細書の分析専門家です。
請求項の本文から核心的な構成要素を抽出し、発明の詳細な説明のどの段落でその構成要素が説明されているかをマッピングします。

출력 형식 (JSON만, 다른 텍스트 없이):
{
  "청구항분석": [
    {
      "청구항번호": 1,
      "유형": "독립항",
      "인용항": [],
      "구성요소": [
        {
          "id": "A",
          "명칭": "タイヤ成形金型",
          "텍스트": "（請求項原文からそのまま抜粋・省略なし）",
          "관련단락": ["[0008]", "[0014]"],
          "매핑근거": "[0008]段落でこの構成要素の基本構造を説明している"
        }
      ]
    }
  ]
}

규칙:
1. 텍스트 필드는 청구항 원문에서 해당 구성요소 부분을 한 글자도 빠짐없이 그대로 복사하세요. 생략 절대 금지.
2. 청구항 마지막의 발명 명칭（例: 「〜装置」「〜タイヤ」「〜方法」）은 구성요소로 분리하지 마세요.
3. 관련단락은 위 단락 목록에 실제로 있는 번호만 사용하세요. 없는 번호를 만들지 마세요.
4. 구성요소는 청구항 본문에서 읽점（、）、세미콜론、줄바꿈으로 구분되는 실질적 기술 요소 단위로 분리하세요."""

    claims_text = "\n\n".join(
        f"[請求項{c['청구항번호']}] ({c['유형']}, 引用項: {c['인용항']})\n{c['본문']}"
        for c in target_claims
    )

    user_prompt = f"""特許: {pub_num}
概要: {title}

== 分析対象請求項 ==
{claims_text}

== 発明の詳細な説明 段落リスト（番号: 内容冒頭） ==
{para_list_text}

各請求項の구성요소를 분리하고 어느 단락에서 설명되는지 매핑해주세요."""

    result_text = ""
    usage = {}
    stream = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        stream=True,
        stream_options={"include_usage": True},
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_prompt},
        ]
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            result_text += delta
            print(delta, end="", flush=True)
        if chunk.usage:
            usage = chunk.usage
    print()

    json_match = re.search(r"```json\s*([\s\S]+?)\s*```", result_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        brace_match = re.search(r'\{[\s\S]*\}', result_text)
        json_str = brace_match.group(0) if brace_match else result_text.strip()

    try:
        llm_result = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"\n[경고] JSON 파싱 실패: {e}")
        llm_result = {"청구항분석": [], "llm_raw": result_text}

    return {
        "공보번호":    pub_num,
        "공개일":      patent_json.get("공개일"),
        "청구항구조": parsed_claims,
        **llm_result,
        "_usage": {
            "input_tokens":  getattr(usage, "prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0),
        }
    }


# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    BASE = Path(__file__).parent

    if len(sys.argv) < 2:
        print("사용법: python JP_tool2.py <jp_json파일> [청구항번호,...]")
        print("예시:   python JP_tool2.py JP_Cited_Patents/output/JP200600150602A0.json")
        print("        python JP_tool2.py JP_Cited_Patents/output/JP200600150602A0.json 1,2")
        sys.exit(0)

    patent_path = Path(sys.argv[1])
    target_nums = None
    if len(sys.argv) >= 3:
        target_nums = [int(x) for x in sys.argv[2].split(",")]

    with open(patent_path, encoding="utf-8") as f:
        patent_json = json.load(f)

    print(f"[JP_tool2] 분석 중: {patent_path.name}")
    print(f"  대상 청구항: {target_nums if target_nums else '독립항 전체'}")

    result = jp_tool2(patent_json, target_nums)

    out_path = BASE / "JP_Cited_Patents" / "output" / f"jp_tool2_{patent_path.stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장: {out_path}")
