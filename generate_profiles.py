"""SFW 프로필 이미지 생성 스크립트 — char01~char06
persona JSON의 image_prompt_prefix / image_negative_prefix 사용
"""

import asyncio
import json
import shutil
from pathlib import Path

# dotenv 로드 (ComfyUI URL 등 환경변수 필요)
from dotenv import load_dotenv
load_dotenv()

from src.comfyui import generate_image

PROJECT_ROOT = Path(__file__).resolve().parent
PROFILE_DIR = PROJECT_ROOT / "images" / "profile"
PERSONA_DIR = PROJECT_ROOT / "persona"
IMAGES_DIR = PROJECT_ROOT / "images"

CHAR_IDS = ["char10"]

# 프로필용 공통 태그 (SFW, 얼굴 중심, 흰 배경)
PROFILE_SUFFIX = "upper body, portrait, centered face, face visible, full head in frame, looking at viewer, smile, fully clothed, white background, simple background"
# kuudere 등 smile 부적합 캐릭터용 (smile 대신 neutral expression)
PROFILE_SUFFIX_NEUTRAL = "upper body, portrait, centered face, face visible, full head in frame, looking at viewer, neutral expression, fully clothed, white background, simple background"
SFW_NEGATIVE = "nude, nsfw, nipples, underwear, panties, pubic hair, exposed, cleavage, see-through, bare shoulders, naked, cropped head, cropped face, cropped forehead, cropped chin, (out of frame:1.3), full body, cowboy shot, lower body, from below, from behind, zoomed out"

# 캐릭터별 오버라이드 — 기본 happy 대신 다른 mood/suffix 사용
CHAR_OVERRIDES = {
    "char10": {
        "expression_key": "blunt",   # kuudere: 평온한 무표정
        "suffix": PROFILE_SUFFIX_NEUTRAL,  # smile 제거
    },
}

# clothing에서 제거할 가슴/하체 포커스 태그 — 얼굴 중심 프로필에서는 제외
_EXCLUDE_FROM_PROFILE_CLOTHING = {
    "deep_cleavage", "cleavage", "plunging_neckline", "exposed_cleavage",
    "sideboob", "underboob", "breast_focus", "huge_breasts",
    "side_slit", "thigh_slit", "micro_bikini", "bikini",
    "lace_trim",  # 노이즈
}


def _filter_profile_clothing(clothing: str) -> str:
    """clothing 문자열에서 가슴/하체 포커스 태그 제거 (프로필용)."""
    tags = [t.strip() for t in clothing.split(",") if t.strip()]
    kept = [t for t in tags if t.lower() not in _EXCLUDE_FROM_PROFILE_CLOTHING]
    return ", ".join(kept)


async def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = []

    for char_id in CHAR_IDS:
        # persona JSON에서 프롬프트 로드
        persona_path = PERSONA_DIR / f"{char_id}.json"
        with open(persona_path, "r", encoding="utf-8") as f:
            persona = json.load(f)

        # images/char*.json에서 clothing + expressions 태그 로드
        img_config_path = IMAGES_DIR / f"{char_id}.json"
        clothing = ""
        expression_tags = ""
        override = CHAR_OVERRIDES.get(char_id, {})
        expression_key = override.get("expression_key", "happy")
        suffix = override.get("suffix", PROFILE_SUFFIX)
        if img_config_path.exists():
            with open(img_config_path, "r", encoding="utf-8") as f2:
                img_config = json.load(f2)
            clothing = _filter_profile_clothing(img_config.get("clothing", ""))
            expressions = img_config.get("expressions", {})
            if expression_key in expressions:
                expression_tags = expressions[expression_key]

        name = persona.get("name", char_id)
        pos_prefix = persona.get("image_prompt_prefix", "")
        neg_prefix = persona.get("image_negative_prefix", "")

        parts = [pos_prefix, clothing, expression_tags, suffix]
        pos_prompt = ", ".join(p for p in parts if p)
        neg_prompt = f"{neg_prefix}, {SFW_NEGATIVE}" if neg_prefix else SFW_NEGATIVE

        print(f"\n[{char_id}] {name} — 생성 시작...")
        print(f"  pos: {pos_prompt[:80]}...")
        try:
            result_path = await generate_image(
                pos_prompt=pos_prompt,
                neg_prompt=neg_prompt,
                orientation="portrait",
                seed=0,
                skip_face=True,
            )
            if result_path is None:
                print(f"[{char_id}] 생성 실패 (None 반환)")
                failed.append(char_id)
                continue

            dest = PROFILE_DIR / f"{char_id}.png"
            shutil.copy2(result_path, dest)
            print(f"[{char_id}] 완료 → {dest}")
            success += 1

        except Exception as e:
            print(f"[{char_id}] 에러: {e}")
            failed.append(char_id)

    print(f"\n완료: {success}/{len(CHAR_IDS)} 성공", end="")
    if failed:
        print(f", 실패: {', '.join(failed)}")
    else:
        print()


if __name__ == "__main__":
    asyncio.run(main())
