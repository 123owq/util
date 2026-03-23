"""
sa2_tool2.py - SA-2 Tool 2: 청구항 파싱 + 상세설명 단락 매핑

구조 원칙:
  코드  → 확정적 처리 (독립항/종속항 구분, 인용 항번호 추출)
  LLM   → 의미 분석 (구성요소 추출, 단락 매핑)
"""

import json
import re
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
MODEL = "deepseek/deepseek-chat-v3.1"


def _parse_claim_structure(claims: list[dict]) -> list[dict]:
    """
    코드로 청구항 구조 파싱 (독립항/종속항 구분, 인용 항번호 추출)
    """
    parsed = []
    for claim in claims:
        num = claim["청구항번호"]
        text = claim["내용"]

        m = re.match(r"^제\s*(\d+)\s*항(?:\s+내지\s+제\s*(\d+)\s*항)?\s+중\s+어느\s+한\s+항에\s+(?:있어서|따른),?\s*", text)
        if m:
            if m.group(2):
                parents = list(range(int(m.group(1)), int(m.group(2)) + 1))
            else:
                parents = [int(m.group(1))]
            body = text[m.end():].strip()
            claim_type = "종속항"
        else:
            m2 = re.match(r"^제\s*(\d+)\s*항에\s+있어서,?\s*", text)
            if m2:
                parents = [int(m2.group(1))]
                body = text[m2.end():].strip()
                claim_type = "종속항"
            else:
                parents = []
                body = text
                claim_type = "독립항"

        parsed.append({
            "청구항번호": num,
            "유형": claim_type,
            "인용항": parents,
            "본문": body,
        })

    return parsed


def _build_description_index(description: list[dict]) -> dict[str, str]:
    """발명의설명 → { "[0001]": "본문 내용...", ... }"""
    index = {}
    for section in description:
        for para in section.get("단락", []):
            num = para.get("번호", "")
            content = para.get("내용", "")
            if num:
                index[num] = content[:300]
    return index


def sa2_tool2(patent_json: dict, target_claim_nums: list[int] = None) -> dict:
    """
    특허 JSON → 청구항 구성요소 파싱 + 상세설명 단락 매핑

    target_claim_nums: None이면 독립항만 처리, 지정하면 해당 항만 처리
    """
    claims = patent_json.get("청구범위", [])
    description = patent_json.get("발명의설명", [])
    biblio = patent_json.get("서지사항", {})

    parsed_claims = _parse_claim_structure(claims)

    if target_claim_nums is not None:
        target_claims = [c for c in parsed_claims if c["청구항번호"] in target_claim_nums]
    else:
        target_claims = [c for c in parsed_claims if c["유형"] == "독립항"]

    para_index = _build_description_index(description)
    para_list_text = "\n".join(
        f"{num}: {content[:150]}..."
        for num, content in list(para_index.items())[:80]
    )

    system = """당신은 특허 명세서 분석 전문가입니다.
청구항 본문에서 핵심 구성요소를 추출하고, 상세한 설명의 어느 단락에서 해당 구성요소를 설명하는지 매핑합니다.

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
          "명칭": "흡음재 패드",
          "텍스트": "양면 접착층이 마련되는 저면으로부터 상면까지 관통 형성되는 복수 개의 타공부를 포함하여 적어도 2개 이상 적층되는 흡음재 패드",
          "관련단락": ["[0010]", "[0025]", "[0031]"],
          "매핑근거": "0010단락에서 흡음재 패드의 기본 구조를 설명함"
        }
      ]
    }
  ]
}

규칙:
1. 텍스트 필드는 청구항 원문에서 해당 구성요소 부분을 한 글자도 빠짐없이 그대로 복사하세요. "..." 또는 어떠한 생략도 절대 금지합니다. 원문이 길어도 전부 복사하세요.
2. 청구항 마지막의 발명 명칭(예: "~장치", "~시스템", "~방법", "~타이어")은 구성요소로 분리하지 마세요.
3. 관련단락은 위 단락 목록에 실제로 있는 번호만 사용하세요. 없는 번호를 만들지 마세요.
4. 구성요소는 청구항 본문에서 세미콜론(;), 쉼표, 줄바꿈으로 구분되는 실질적 기술 요소 단위로 분리하세요."""

    claims_text = "\n\n".join(
        f"[청구항 {c['청구항번호']}] ({c['유형']}, 인용항: {c['인용항']})\n{c['본문']}"
        for c in target_claims
    )

    user_prompt = f"""특허: {biblio.get('발명의명칭', '')}

== 분석 대상 청구항 ==
{claims_text}

== 상세한 설명 단락 목록 (번호: 내용 앞부분) ==
{para_list_text}

각 청구항의 구성요소를 분리하고 어느 단락에서 설명되는지 매핑해주세요."""

    result_text = ""
    usage = {}
    stream = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        stream=True,
        stream_options={"include_usage": True},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
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
    json_str = json_match.group(1) if json_match else result_text.strip()
    llm_result = json.loads(json_str)

    return {
        "출원번호": biblio.get("출원번호"),
        "발명의명칭": biblio.get("발명의명칭"),
        "청구항구조": parsed_claims,
        **llm_result,
        "_usage": {
            "input_tokens": getattr(usage, "prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0),
        }
    }


if __name__ == "__main__":
    import sys

    BASE = Path(__file__).parent

    if len(sys.argv) < 2:
        print("사용법: python sa2_tool2.py <특허_json파일> [청구항번호,...]")
        print("예시:   python sa2_tool2.py patent_parsing/output/1020240124655A.json 1")
        print("        python sa2_tool2.py patent_parsing/output/1020240124655A.json 1,2,3")
        sys.exit(0)

    patent_path = Path(sys.argv[1])
    target_nums = None
    if len(sys.argv) >= 3:
        target_nums = [int(x) for x in sys.argv[2].split(",")]

    with open(patent_path, encoding="utf-8") as f:
        patent_json = json.load(f)

    print(f"[Tool 2] 특허 분석 중: {patent_path.name}")
    print(f"  대상 청구항: {target_nums if target_nums else '독립항 전체'}")

    result = sa2_tool2(patent_json, target_nums)

    out_path = BASE / "patent_parsing" / "output" / f"sa2_tool2_{patent_path.stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장: {out_path}")
