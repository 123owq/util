"""
sa2_tool1.py - SA-2 Tool 1: OA JSON → 청구항별 거절이유 구조화

구조 원칙:
  코드  → 확정적 처리 (청구항 범위 파싱)
  LLM   → 의미 분석 (거절이유 분류, 핵심내용 추출)
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


def _parse_claim_range(text: str) -> list[int]:
    """
    "청구항 제1항, 제3항"             → [1, 3]
    "청구항 제1항 내지 제5항"         → [1,2,3,4,5]
    "청구항 제2항 내지 제3항, 제7항"  → [2,3,7]  ← 내지+콤마 혼용
    "청구항 전항"                      → []
    """
    if "전항" in text:
        return []

    result = set()
    # 1) "제X항 내지 제Y항" 범위를 먼저 처리
    for m in re.finditer(r"제(\d+)항\s*내지\s*제(\d+)항", text):
        result.update(range(int(m.group(1)), int(m.group(2)) + 1))
    # 2) 범위 구간 제거 후 남은 개별 항번호 추출
    remaining = re.sub(r"제\d+항\s*내지\s*제\d+항", "", text)
    for m in re.finditer(r"제(\d+)항", remaining):
        result.add(int(m.group(1)))

    return sorted(result)


def _parse_total_claims(oa_json: dict) -> int:
    """심사대상청구항('제1-10항' 등)에서 총 항수 파싱"""
    target = oa_json.get("심사결과", {}).get("심사대상청구항", "")
    m = re.search(r"제\d+[-~](\d+)항", target)
    if m:
        return int(m.group(1))
    m = re.search(r"제(\d+)항", target)
    return int(m.group(1)) if m else 0


def sa2_tool1(oa_json: dict) -> dict:
    """
    OA JSON(extract_v6.py 출력) → 청구항별 거절이유 구조화

    코드 단계:
      1. 거절이유표에서 (청구항 범위, 법조항) 매핑 추출
      2. 구체적거절이유 sections를 텍스트로 직렬화

    LLM 단계:
      3. 구체적 거절이유 본문을 읽고 청구항별 세부 설명 생성
    """
    meta = oa_json.get("meta", {})
    rejection_table = oa_json.get("심사결과", {}).get("거절이유표", [])
    sections = oa_json.get("구체적인거절이유", {}).get("sections", [])
    total_claims = _parse_total_claims(oa_json)

    # ── 1. 거절이유표 코드 파싱 ─────────────────────────────────────────────
    table_rows = []
    for row in rejection_table:
        claims_text = row.get("거절이유가 있는 부분", "")
        law = row.get("관련 법조항", "")
        claims = _parse_claim_range(claims_text)
        # "전항" → 총 항수로 확장
        if not claims and "전항" in claims_text and total_claims:
            claims = list(range(1, total_claims + 1))
        table_rows.append({
            "순번": row.get("순번"),
            "claims_text": claims_text,
            "parsed_claims": claims,
            "법조항": law
        })

    # ── 2. sections 직렬화 (LLM 입력용) ──────────────────────────────────────
    # 헤더에서 섹션 번호 코드로 추출 → LLM이 번호를 직접 복사할 수 있도록
    sections_text = ""
    for sec in sections:
        header = sec["header"]
        m = re.match(r"^(\d+(?:-\d+)?)[\.\)]", header)
        sec_num = m.group(1) if m else "?"
        sections_text += f"[섹션 {sec_num}] {header}\n{sec['content']}\n"
        if sec.get("비교표"):
            tbl = sec["비교표"]
            sections_text += "  비교표 헤더: " + " | ".join(tbl["원본_헤더"]) + "\n"
            for r in tbl["rows"]:
                sections_text += "  " + " | ".join(str(r.get(h, "")) for h in tbl["원본_헤더"]) + "\n"
        sections_text += "\n"

    # ── 3. LLM 호출 ──────────────────────────────────────────────────────────
    system = """당신은 특허 심사대응 전문가입니다.
의견제출통지서의 구체적 거절이유를 분석하여 JSON으로 구조화합니다.

출력 형식 (JSON만 출력, 다른 텍스트 없이):
{
  "청구항별거절이유": [
    {
      "청구항번호": 1,
      "거절이유목록": [
        {
          "거절이유번호": "2-1",
          "법조항": "특허법 제29조제1항제2호",
          "유형": "신규성",
          "인용발명": ["인용발명 1"],
          "핵심내용": "인용발명 1과 실질적으로 동일한 발명임",
          "지적구성요소": ["카카스부", "안테나"],
          "비교표있음": true
        }
      ]
    }
  ]
}

규칙:
1. 거절이유번호는 구체적 거절이유 전문의 [섹션 X] 태그에 있는 번호(예: 1, 1-1, 1-2, 2, 2-1 등)를 그대로 복사하세요. 절대 축약하거나 새 번호를 만들지 마세요. 상위 섹션(예: [섹션 2])보다 하위 섹션(예: [섹션 2-1])이 해당 청구항을 구체적으로 다루는 경우 하위 섹션 번호를 사용하세요.
2. 각 청구항에 어떤 거절이유가 적용되는지는 아래 거절이유표의 parsed_claims 배열을 기준으로 판단하세요.
3. 구체적 거절이유 본문에서 해당 청구항에 대한 설명을 찾아 핵심내용을 작성하세요.
4. 본문에 구체적 설명이 없는 청구항이라도 parsed_claims에 포함된 경우, 해당 거절이유 유형과 법조항만 기재하고 핵심내용은 "전항에 동일 적용"으로 작성하세요.
5. 청구항번호 순서(1, 2, 3 ...)로 정렬하여 출력하세요.
6. 유형 분류: 신규성(제29조1항), 진보성(제29조2항), 기재불비(제42조4항), 보정각하, 기타"""

    user_prompt = f"""다음 의견제출통지서 정보를 분석하여 청구항별 거절이유를 구조화해주세요.

== 거절이유표 (parsed_claims에 포함된 항번호가 해당 거절이유 대상) ==
{json.dumps(table_rows, ensure_ascii=False, indent=2)}

== 구체적 거절이유 전문 ==
{sections_text}

청구항 1번부터 {total_claims}번까지 각각 어떤 거절이유를 받았는지 JSON으로 출력하세요."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
    )

    text_out = response.choices[0].message.content
    json_match = re.search(r"```json\s*([\s\S]+?)\s*```", text_out)
    json_str = json_match.group(1) if json_match else text_out.strip()
    llm_result = json.loads(json_str)

    # 유형 필드 정규화 (LLM이 한자 혼용할 수 있음: 진보性 → 진보성)
    _유형_map = {"진보性": "진보성", "신규性": "신규성"}
    for claim_item in llm_result.get("청구항별거절이유", []):
        for reason in claim_item.get("거절이유목록", []):
            reason["유형"] = _유형_map.get(reason.get("유형", ""), reason.get("유형", ""))

    return {
        "출원번호": meta.get("출원번호"),
        "발명의명칭": meta.get("발명의명칭"),
        "인용발명": meta.get("인용발명", []),
        "거절이유표_원본": table_rows,
        **llm_result,
        "_usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }
    }


if __name__ == "__main__":
    import sys

    BASE = Path(__file__).parent

    if len(sys.argv) < 2:
        print("사용법: python sa2_tool1.py <OA_json파일>")
        print("예시:   python sa2_tool1.py OA_parsing/output/OA4_v6.json")
        sys.exit(0)

    oa_path = Path(sys.argv[1])
    with open(oa_path, encoding="utf-8") as f:
        oa_json = json.load(f)

    print(f"[Tool 1] OA 분석 중: {oa_path.name}")
    result = sa2_tool1(oa_json)

    out_path = BASE / "OA_parsing" / "output" / f"sa2_tool1_{oa_path.stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장: {out_path}")
