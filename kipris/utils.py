import os                            # 디렉토리 생성용
import re                            # 정규식용
import json                          # JSON 저장용
import xml.etree.ElementTree as ET   # XmaxML 타입 힌트용


def safe_dirname(s: str, max_len=60) -> str:
    """폴더명으로 쓸 수 없는 문자 제거 후 길이 제한"""
    return re.sub(r'[\\/:*?"<>|]', '_', s).strip()[:max_len]  # 특수문자 → 밑줄, 앞뒤 공백 제거, 최대 60자


def save_json(data, path: str):
    """data를 JSON 파일로 저장. 부모 디렉토리가 없으면 자동 생성."""
    os.makedirs(os.path.dirname(path), exist_ok=True)           # 저장 경로의 폴더 없으면 생성
    with open(path, "w", encoding="utf-8") as f:                # UTF-8로 파일 열기
        json.dump(data, f, ensure_ascii=False, indent=2)        # 한글 유지, 들여쓰기 2칸


def xml_to_dict(element: ET.Element) -> dict:
    """XML Element를 dict로 변환. 같은 태그가 여러 개면 리스트로 묶음."""
    result = {}
    for child in element:                                        # 자식 요소 순회
        tag   = child.tag.split("}")[-1]                        # '{namespace}tag' → 'tag' (namespace 제거)
        value = xml_to_dict(child) if len(child) else (child.text or "")  # 자식이 있으면 재귀, 없으면 텍스트
        if tag in result:                                        # 같은 태그가 이미 있으면
            if not isinstance(result[tag], list):               # 아직 리스트가 아니면
                result[tag] = [result[tag]]                     # 기존 값을 리스트로 변환
            result[tag].append(value)                           # 새 값 추가
        else:
            result[tag] = value                                 # 첫 등장이면 그냥 대입
    return result


def find_all(root: ET.Element, tag: str) -> list[ET.Element]:
    """namespace 유무에 상관없이 tag 이름으로 모든 요소 검색"""
    results = root.findall(f".//{tag}")  # namespace 없는 경우
    if results:
        return results
    # namespace가 붙은 경우: {http://...}tag 형태이므로 끝이 }tag 인 요소를 직접 순회
    return [el for el in root.iter() if el.tag == tag or el.tag.endswith(f"}}{tag}")]
