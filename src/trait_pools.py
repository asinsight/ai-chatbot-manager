"""
trait_pools.py — Danbooru tag pools + random-character composition utilities (SFW fork)

Module that random-samples appearance / body / clothing tags from curated
pools for the image-generator bot's `/random` (SFW) flow. Situational tags
(pose / expression / location) are decided autonomously by Grok, so this file
holds only "identity"-level fixed tags.

Uses stdlib only (`random`) — no DB / API dependencies.
"""

import json
import logging
import os
import random
from pathlib import Path

logger = logging.getLogger(__name__)


def dedup_tags(tag_string: str) -> str:
    """Dedupe tags in a comma-separated tag string. Preserves order."""
    seen = set()
    result = []
    for tag in tag_string.split(","):
        tag = tag.strip()
        if not tag:
            continue
        key = tag.lower().strip("() ").split(":")[0]
        if key not in seen:
            seen.add(key)
            result.append(tag)
    return ", ".join(result)


# ============================================================
# PART 1: APPEARANCE — fixed; the foundation of cross-render consistency
# ============================================================

HAIR_COLOR = [
    # ── Basic & Natural ──
    "blonde_hair", "black_hair", "brown_hair", "light_brown_hair", "dark_brown_hair",
    "red_hair", "auburn_hair", "orange_hair",
    # ── Fantasy / Vibrant (saturation tuned — drop fluorescent/neon, prefer muted alternatives) ──
    "blue_hair", "light_blue_hair", "dark_blue_hair", "teal_hair", "turquoise_hair",
    "pink_hair", "light_pink_hair", "coral_hair",
    "purple_hair", "light_purple_hair", "violet_hair",
    "green_hair", "olive_hair", "emerald_hair",
    "white_hair", "silver_hair", "grey_hair", "platinum_blonde_hair",
    "ash_blonde_hair", "strawberry_blonde_hair", "golden_blonde_hair",
    # ── Special ──
    "multicolored_hair", "two-tone_hair", "three-tone_hair", "gradient_hair",
    "ombre_hair", "pastel_hair", "chestnut_hair",
]

HAIR_STYLE = [
    # ── Length ──
    "long_hair", "very_long_hair", "short_hair", "medium_hair", "shoulder-length_hair",
    # ── Classic Styles ──
    "bob_cut", "pixie_cut", "hime_cut", "princess_cut",
    "ponytail", "high_ponytail", "low_ponytail", "side_ponytail",
    "twintails", "low_twintails", "high_twintails", "drill_hair", "odango",
    "braids", "french_braid", "side_braid", "single_braid", "twin_braids",
    # ── Buns & Updos ──
    "hair_bun", "double_bun", "bun_head", "messy_bun",
    # ── Messy & Casual ──
    "messy_hair", "bedhead", "disheveled_hair", "fluffy_hair",
    "straight_hair", "wavy_hair", "curly_hair", "ringlets", "spiral_curls",
    # ── Special Anime Styles ──
    "ahoge", "antenna_hair", "jellyfish_cut", "wolf_cut", "shaggy_hair",
    "hair_over_one_eye", "hair_over_eyes", "hair_between_eyes",
    "sidelocks", "long_sidelocks", "front_ponytail", "half_updo",
]

BANGS = [
    "bangs", "blunt_bangs", "side_swept_bangs", "parted_bangs", "curtain_bangs",
    "hair_between_eyes", "swept_bangs", "long_bangs", "short_bangs",
    "asymmetrical_bangs", "choppy_bangs", "wispy_bangs", "layered_bangs",
    "thick_bangs", "thin_bangs", "bangs_over_eyes", "see-through_bangs",
    "uneven_bangs", "zigzag_bangs", "heart-shaped_bangs",
]

EYE_COLOR = [
    # ── Natural ──
    "blue_eyes", "light_blue_eyes", "dark_blue_eyes",
    "green_eyes", "emerald_eyes", "lime_eyes",
    "brown_eyes", "dark_brown_eyes", "hazel_eyes",
    "grey_eyes", "silver_eyes",
    # ── Fantasy / Striking ──
    "red_eyes", "crimson_eyes", "scarlet_eyes",
    "purple_eyes", "violet_eyes", "lavender_eyes",
    "yellow_eyes", "golden_eyes", "amber_eyes",
    "pink_eyes", "magenta_eyes",
    "aqua_eyes", "cyan_eyes", "turquoise_eyes",
    "orange_eyes", "heterochromia", "multi-colored_eyes",
]

EYE_SHAPE = [
    # ── Identity (shape only, no expression state) ──
    "sharp_eyes", "tsurime", "droopy_eyes", "tareme",
    "round_eyes", "narrow_eyes", "upturned_eyes", "downturned_eyes",
    "almond_eyes", "sanpaku", "large_eyes", "small_eyes",
    "slanted_eyes", "cat_eyes", "fox_eyes", "doe_eyes",
    "hooded_eyes", "monolid_eyes", "double_eyelid",
    "detailed_pupils", "long_eyelashes",
]

EYEBROW = [
    # ── Shape ──
    "thin_eyebrows", "thick_eyebrows",
    "straight_eyebrows", "arched_eyebrows", "curved_eyebrows",
    "short_eyebrows", "long_eyebrows",
    "plucked_eyebrows", "gyaru_eyebrows",
    # ── Light styling ──
    "light_eyebrows", "dark_eyebrows",
]

NOSE = [
    # ── Shape identity ──
    "pointy_nose", "sharp_nose", "aquiline_nose",
    "small_nose", "button_nose", "snub_nose",
    "upturned_nose", "flat_nose", "rounded_nose",
    "nose_bridge",
]

SKIN_TONE = [
    # ── Light ──
    "pale_skin", "fair_skin", "light_skin", "ivory_skin",
    # ── Medium / Natural ──
    "tan", "light_tan", "golden_skin", "beige_skin",
    # ── Dark ──
    "dark_skin", "dark-skinned_female", "brown_skin", "deep_brown_skin",
    "very_dark_skin", "ebony_skin",
    # ── Special ──
    "albino", "porcelain_skin", "flawless_skin", "sunburned_skin",
    "freckles", "freckled_skin", "blushing_skin",
]

# Species (fantasy setting, humanoid only)
# None = plain human (no tag)
SPECIES = [
    # Human weighting (8/21 ≈ 38% — re-tuned from the previous 40% along with hat-less witch etc.)
    None, None, None, None, None, None, None, None,
    "elf, pointy_ears",
    "dark_elf, dark-skinned_female, pointy_ears",
    "half-elf, pointy_ears",
    "demon_girl, demon_horns",
    "demon_girl, demon_horns, demon_tail",
    "angel, angel_wings, halo",
    "fallen_angel, black_wings, halo",
    "vampire, fangs, red_eyes",
    "witch",  # The hat is decided by clothing / accessories — do not force it into the species tag
    "fox_girl, fox_ears, fox_tail",
    "cat_girl, cat_ears, cat_tail",
    "wolf_girl, wolf_ears, wolf_tail",
    "dragon_girl, dragon_horns, dragon_tail",
    "succubus, demon_horns, demon_wings, demon_tail",
    "fairy, fairy_wings, small_wings",
]

# ============================================================
# PART 2: BODY — fixed
# ============================================================

# ── Split by category — roll_body() samples each category with an independent probability ──

# Height (SIZE) — only one value per character
BODY_SIZE = [
    "petite", "short", "shortstack", "medium_height", "tall_female",
]

# Base build (BUILD) — overall skeletal/flesh impression
BODY_BUILD = [
    # Slim
    "slim", "slender", "skinny", "delicate", "fragile",
    # Athletic
    "athletic_build", "toned", "fit", "muscular_female",
    # Plump
    "plump", "chubby", "slightly_chubby", "thick", "soft_body",
]

# Line (CURVE) — emphasises curves / proportions (optional)
BODY_CURVE = [
    "curvy", "voluptuous", "hourglass_figure", "pear_shaped_figure",
    "busty", "curvaceous",
    "narrow_waist", "small_waist",
    "wide_hips", "childbearing_hips", "thick_hips",
    "thick_thighs", "plump_thighs", "thicc_thighs",
    "long_legs", "long_torso", "short_torso",
]

# Highlight detail (ACCENT) — only mixed in occasionally
BODY_ACCENT = [
    "abs", "defined_abs", "visible_ribs", "collarbone", "sharp_collarbone",
]

# Butt is consolidated into its own ASS category
BODY_ASS = [
    "big_ass", "huge_ass", "plump_ass", "round_ass",
    "bubble_butt", "heart-shaped_ass", "wide_ass", "thick_ass", "jiggly_ass",
]

# Breast size — pure size only (excludes flat_chest, which conflicts with the adult rule)
BREAST_SIZE = [
    # Small
    "tiny_breasts", "small_breasts", "petite_breasts",
    # Medium
    "medium_breasts", "average_breasts",
    # Large+
    "large_breasts", "huge_breasts", "gigantic_breasts",
    "massive_breasts", "enormous_breasts", "colossal_breasts",
    "heavy_breasts", "hanging_breasts",
]

# Breast shape/framing — detail that can be added independently of size
BREAST_FEATURE = [
    "perky_breasts", "round_breasts", "teardrop_breasts",
    "sideboob", "underboob", "cleavage", "deep_cleavage", "breast_focus",
]

# ============================================================
# PART 3: CLOTHING — per setting, mutable
# Use colors / items EXACTLY — never substitute.
# ============================================================

CLOTHING_SETS = {
    # ── School Uniforms ──
    "school_uniform_a": "white_shirt, blue_ribbon, pleated_skirt, blue_skirt, kneehighs, white_kneehighs, loafers, frills, sailor_collar, school_uniform",
    "school_uniform_b": "serafuku, sailor_collar, red_neckerchief, pleated_skirt, navy_skirt, thighhighs, black_thighhighs, frilled_sleeves, school_uniform",
    "school_uniform_c": "blazer, grey_blazer, white_shirt, plaid_skirt, red_plaid, loose_socks, school_uniform, vest",
    "school_uniform_d": "sailor_uniform, blue_serafuku, pleated_skirt, white_shirt, red_ribbon, black_thighhighs, loafers",
    "school_uniform_e": "gakuran, male_school_uniform, black_uniform, white_shirt, red_necktie, black_pants, school_uniform",
    "sailor_fuku": "sailor_fuku, long_sleeves, pleated_skirt, neckerchief, thighhighs, frills",

    # ── Office / Professional ──
    "office_formal": "white_blouse, black_pencil_skirt, black_pantyhose, high_heels, blouse, tight_skirt, cleavage, pantyhose",
    "office_casual": "cream_blouse, grey_slacks, cardigan, flats, office_lady, collared_shirt",
    "secretary": "secretary, white_blouse, tight_skirt, pantyhose, glasses, high_heels, clipboard",
    "teacher": "teacher, white_blouse, pencil_skirt, glasses, pantyhose, high_heels, pointer",
    "flight_attendant": "flight_attendant, uniform, pencil_skirt, scarf, pillbox_hat, pantyhose, high_heels, stewardess",
    "pilot_uniform": "pilot, uniform, hat, gloves, necktie, black_pantyhose, boots, captain_hat",

    # ── Casual / Daily ──
    "casual_summer": "white_crop_top, blue_denim_shorts, sneakers, navel, midriff, short_shorts",
    "casual_winter": "oversized_sweater, black_leggings, scarf, boots, turtleneck, sweater",
    "casual_dress": "sundress, floral_print, sandals, straw_hat, bare_shoulders, summer_dress",
    "hoodie_cozy": "oversized_hoodie, shorts_under_hoodie, thighhighs, bare_legs, hoodie, off_shoulder",
    "tank_top_casual": "tank_top, white_tank_top, denim_skirt, sneakers, baseball_cap, navel",
    "leather_jacket": "leather_jacket, black_tank_top, ripped_jeans, combat_boots, choker, cropped_jacket",
    "off_shoulder": "off-shoulder_sweater, collarbone, bare_shoulders, skirt, thighhighs, off_shoulder",
    "tube_top": "tube_top, white_tube_top, hotpants, sandals, navel, strapless",
    "crop_top_skirt": "crop_top, navel, miniskirt, thighhighs, sneakers, midriff",

    # ── Maid / Service ──
    "maid_classic": "maid_headdress, maid_apron, black_dress, white_apron, frills, thighhighs, white_thighhighs, puffy_sleeves, maid",
    "maid_cafe": "maid_headdress, pink_dress, white_apron, frills, kneehighs, mary_janes, maid, frilled_apron",
    "waitress": "waitress, white_blouse, black_skirt, apron, name_tag, flats, frills, maid_apron",

    # ── Fantasy / Cosplay ──
    "fantasy_mage": "robe, hooded_robe, staff, thigh_boots, corset, belt, magic",
    "fantasy_knight": "armor, breastplate, gauntlets, cape, thigh_boots, circlet, plate_armor",
    "fantasy_elf": "white_dress, leaf_ornament, cape, sandals, pointed_ears, elf",
    "fantasy_demon": "black_corset, torn_cape, thigh_boots, horns, demon_tail, succubus",
    "vampire_dress": "vampire, gothic_dress, red_eyes, choker, cape, high_heels, black_gloves",
    "princess_dress": "princess, tiara, ball_gown, white_dress, elbow_gloves, jewelry, high_heels",
    "witch": "black_robe, belt, thigh_boots, staff, cape, witch",
    "steampunk": "steampunk, corset, goggles, top_hat, gears, thigh_boots, gloves, steampunk",

    # ── Gothic / Lolita ──
    "gothic_lolita": "gothic_lolita, black_dress, petticoat, corset, choker, cross_necklace, platform_shoes, frills",
    "sweet_lolita": "sweet_lolita, pink_dress, frills, petticoat, bow, lace, mary_janes",
    "classic_lolita": "classic_lolita, blue_dress, frills, bonnet, lace, petticoat",

    # ── Traditional / Cultural ──
    "kimono": "kimono, obi, tabi, geta, hair_ornament, floral_kimono, furisode",
    "yukata": "yukata, obi, geta, hair_ornament, fan, festival, summer_kimono",
    "hanbok": "hanbok, jeogori, chima, hair_ribbon, traditional_hair_ornament, korean_clothes",
    "china_dress": "china_dress, red_dress, side_slit, thighhighs, flats, hair_ornament, qipao",
    "qipao_short": "china_dress, short_dress, side_slit, thighhighs, flats, mandarin_collar",
    "shrine_maiden": "miko, hakama, white_kimono, red_hakama, hair_ribbon, tabi, shrine_maiden",

    # ── Swimsuit / Beach ──
    "swimsuit_bikini": "bikini, string_bikini, side-tie_bikini_bottom, sandals, micro_bikini",
    "swimsuit_one": "one-piece_swimsuit, high-leg_swimsuit, barefoot, competition_swimsuit",
    "school_swimsuit": "school_swimsuit, blue_swimsuit, white_trim, nametag, barefoot",

    # ── Sleepwear / Loungewear ──
    "sleepwear_cute": "pajamas, oversized_shirt, shorts, bare_legs, pajama_shirt",

    # ── Idol / Stage / Performer ──
    "idol_stage": "idol_clothes, frills, miniskirt, thighhighs, gloves, hair_ornament, idol, stage",
    "cheerleader": "cheerleader, crop_top, pleated_skirt, pompoms, sneakers, hair_ribbon",
    "dancer_ballet": "ballerina, leotard, tutu, ballet_slippers, hair_bun, tights",
    "belly_dancer": "belly_dancer, bra, harem_pants, veil, navel, barefoot, jewelry, armlet",

    # ── Sports / Gym ──
    "gym_wear": "sports_bra, bike_shorts, sneakers, sweatband, athletic",
    "tennis_uniform": "tennis_uniform, pleated_skirt, white_shirt, visor, wristband, sneakers",
    "volleyball_uniform": "volleyball_uniform, shorts, jersey, kneepads, sneakers, ponytail",
    "track_suit": "tracksuit, jacket, shorts, sneakers, sweatband",

    # ── Uniforms / Roleplay ──
    "nurse": "nurse_cap, white_dress, apron, thighhighs, white_thighhighs, nurse",
    "bunny_girl": "bunny_ears, playboy_bunny, wrist_cuffs, pantyhose, black_pantyhose, bow_tie, high_heels",
    "police_uniform": "police, police_uniform, police_hat, badge, miniskirt, thighhighs, boots",
    "military": "military_uniform, beret, boots, belt, medals, gloves, camouflage",
    "racing_queen": "race_queen, bodysuit, thighhighs, high_heels, gloves, race_queen",
    "pirate": "pirate, pirate_hat, eyepatch, torn_shirt, corset, thigh_boots, belt",

    # ── Special / Form-Fitting ──
    "tight_dress": "tight_dress, pencil_dress, cleavage, high_heels, necklace, bodycon_dress",
    "backless_dress": "backless_dress, bare_back, halterneck, high_heels, hair_up",
    "slit_dress": "dress, side_slit, thigh_strap, high_heels, necklace",
    "mini_skirt_set": "miniskirt, tank_top, navel, thighhighs, boots",

    # ── Seasonal / Festival / Costume ──
    "santa_costume": "santa_costume, red_dress, fur_trim, santa_hat, thighhighs, boots",
    "halloween_witch": "halloween, witch_hat, torn_dress, striped_thighhighs, broom, jack-o'-lantern",
    "halloween_vampire": "halloween, vampire, gothic_dress, cape, fake_fangs, choker, red_eyes",
    "wedding_dress": "wedding_dress, veil, white_dress, elbow_gloves, bouquet, high_heels, bridal",
    "towel_wrap": "towel, bath_towel, wet_hair, bare_shoulders, bare_legs, steam",
    "bathrobe": "bathrobe, white_robe, bare_legs, slippers, wet_hair",
    "coat_winter": "long_coat, scarf, turtleneck, miniskirt, boots, earmuffs",

    # ── Street / Cyber / Modern ──
    "cyberpunk_street": "crop_top, black_jacket, leather_jacket, hotpants, thigh_boots, visor, choker, urban_futuristic",
    "cyberpunk_corpo": "bodysuit, black_bodysuit, high_collar, sleek_boots, earpiece, urban_futuristic",
    "overalls": "overalls, denim, white_shirt, sneakers, rolled_up_sleeves",
    "cowgirl_western": "cowboy_hat, plaid_shirt, denim_shorts, cowboy_boots, belt",
}


# ============================================================
# PART 4: UNDERWEAR — paired with the clothing set
# ============================================================

UNDERWEAR_SETS = {
    # ── Basic & Innocent ──
    "innocent_white": "white_panties, white_bra, frilled_panties, frilled_bra, lace_trim, frills, ribbon, bow_panties",
    "striped": "striped_panties, striped_bra, shimapan, frills",
    "cute_pink": "pink_panties, pink_bra, bow_panties, frilled_panties, frilled_bra, ribbon, lace_trim",
    "lace_white": "white_lace_panties, white_lace_bra, lace_trim, intricate_lace, frills, embroidery",
    "lace_black": "black_lace_panties, black_lace_bra, lace_trim, garter_belt, intricate_lace, garter_straps",
    "sexy_red": "red_panties, red_bra, lace_panties, highleg_panties, lace_trim",
    "thong": "thong, strapless_bra, garter_belt, lace_trim",
    "highleg": "highleg_panties, sports_bra, side-tie_panties",
    "matching_blue": "blue_panties, blue_bra, lace_trim, bow",
    "matching_purple": "purple_panties, purple_bra, satin, lace_trim, frills",
    "shimapan": "shimapan, striped_panties, blue_and_white_striped, frilled_panties",
    "babydoll_set": "babydoll, pink_babydoll, see-through_babydoll, matching_panties, lace_trim",
    "bandeau": "bandeau, strapless, low-rise_panties, lace_trim",
    "ribbon_wrap": "ribbon_bra, ribbon_panties, lots_of_ribbons, bow, gift_wrap, frills",

    # ── Garter / Corset / Full Sets ──
    "garter_full": "garter_belt, garter_straps, thighhighs, lace_panties, lace_bra, panties_over_garter_belt, lace_trim",
    "garter_black": "black_garter_belt, black_thighhighs, black_panties, black_bra, lace_trim, garter_straps",
    "garter_white": "white_garter_belt, white_thighhighs, white_panties, white_bra, lace_trim",
    "garter_red": "red_garter_belt, red_thighhighs, red_panties, red_bra, garter_straps",
    "corset_lingerie": "corset, underbust_corset, thong, garter_belt, thighhighs, lace, garter_straps",

    # ── Lingerie / Boudoir (covered, designer styles) ──
    "teddy_lingerie": "teddy_(clothing), lace_teddy, high_cut, see-through, lace_trim",
    "chemise": "chemise, lace_chemise, see-through, bare_shoulders, lace_trim",

    # ── Matching Colors ──
    "matching_black": "black_panties, black_bra, lace_trim, highleg_panties",
    "matching_white_satin": "white_panties, white_bra, satin, glossy",
    "matching_red_lace": "red_lace_panties, red_lace_bra, garter_belt, thighhighs",
    "matching_navy": "navy_panties, navy_bra, bow, lace_trim",
    "matching_pink_ribbon": "pink_panties, pink_bra, ribbon, bow_panties, frills",
    "matching_green": "green_panties, green_bra, lace_trim, frills",
    "matching_aqua": "aqua_panties, aqua_bra, lace_trim",
    "matching_yellow": "yellow_panties, yellow_bra, frills, ribbon",

    # ── Sports / Functional ──
    "sports_set": "sports_bra, boyshorts, spandex, athletic",
    "string_bikini": "string_panties, string_bra, side-tie",
    "side_tie": "side-tie_panties, halter_bra, string",
    "satin_nightwear": "satin_panties, satin_bra, satin, lace_trim, glossy",

    # ── Patterns ──
    "polka_dot": "polka_dot_panties, polka_dot_bra, frilled_panties, frilled_bra, bow",
    "leopard_print": "leopard_print_panties, leopard_print_bra, animal_print",
    "print_set": "print_panties, print_bra, frills",
    "floral_lace": "floral_lace_panties, floral_lace_bra, embroidery, lace_trim",

    # ── Material & Special ──
    "latex_set": "latex_bra, latex_panties, latex, glossy, shiny_clothes, tight",
    "leather_set": "leather_bra, leather_panties, leather, studded",
    "bustier_set": "bustier, garter_belt, stockings, lace_panties, lace_bra",
    "merry_widow": "merry_widow, corset, garter_belt, lace_panties, thighhighs",
    "cat_lingerie": "cat_lingerie, cat_keyhole_bra, cat_cutout, lace_panties",

    # ── Jewel / Metallic ──
    "emerald_lingerie": "emerald_panties, emerald_bra, green_lace, jewel_tone",
    "sapphire_lingerie": "sapphire_panties, sapphire_bra, blue_lace",
    "gold_lingerie": "gold_bra, gold_panties, metallic, shiny",
    "silver_lingerie": "silver_bra, silver_panties, metallic, shiny",

    # ── Frilly ──
    "frilly_pink": "pink_frilled_panties, pink_frilled_bra, lots_of_frills, lolita_fashion",
}


# ============================================================
# Random composition functions
# ============================================================

def roll_appearance() -> dict:
    """Random composition of appearance tags. Character identity = these tags fixed.

    eye_shape, eyebrow, nose are always included exactly once each (strengthens identity lock).
    """
    hair_color = random.choice(HAIR_COLOR)
    hair_styles = random.sample(HAIR_STYLE, k=random.randint(1, 2))
    bangs = random.choice(BANGS)
    eye_color = random.choice(EYE_COLOR)
    eye_shape = random.choice(EYE_SHAPE)  # always included
    eyebrow = random.choice(EYEBROW)       # always included
    nose = random.choice(NOSE)             # always included
    skin_tone = random.choice(SKIN_TONE)
    species = random.choice(SPECIES)  # None = human

    parts = ["1girl", hair_color] + hair_styles + [bangs, eye_color, eye_shape, eyebrow, nose, skin_tone]
    if species:
        parts.extend(species.split(", "))

    return {
        "hair_color": hair_color,
        "hair_style": hair_styles,
        "bangs": bangs,
        "eye_color": eye_color,
        "eye_shape": eye_shape,
        "eyebrow": eyebrow,
        "nose": nose,
        "skin_tone": skin_tone,
        "species": species,
        "appearance_tags": ", ".join(parts),
    }


def roll_body() -> dict:
    """Probabilistic random composition of body tags.

    Each category is independently included/skipped — avoids tag overload and
    keeps diversity / naturalness high. The model paints a sensible adult-female
    default even with no tags, so "none" is also a valid outcome.
    """
    shape: list[str] = []

    # SIZE (height) — 70%
    if random.random() < 0.7:
        shape.append(random.choice(BODY_SIZE))
    # BUILD (base) — 80%
    if random.random() < 0.8:
        shape.append(random.choice(BODY_BUILD))
    # CURVE (line) — 40%
    if random.random() < 0.4:
        shape.append(random.choice(BODY_CURVE))
    # ACCENT — 20%
    if random.random() < 0.2:
        shape.append(random.choice(BODY_ACCENT))
    # ASS (butt accent) — 25%
    if random.random() < 0.25:
        shape.append(random.choice(BODY_ASS))

    # BREAST_SIZE — included 70% of the time (30% leaves it to the model default)
    breast_parts: list[str] = []
    if random.random() < 0.7:
        breast_parts.append(random.choice(BREAST_SIZE))
    # BREAST_FEATURE — added another 30% (independent from size)
    if random.random() < 0.3:
        breast_parts.append(random.choice(BREAST_FEATURE))

    body_tags = ", ".join(shape + breast_parts)

    return {
        "body_shape": shape,
        "breast": breast_parts,
        "body_tags": body_tags,
    }


def roll_clothing(location: str, clothing_pool: list[str] | None = None) -> dict:
    """Random composition of an outfit + underwear that fits the location.
    If clothing_pool is provided, sample from it (lorebook-driven); otherwise sample from all CLOTHING_SETS."""
    pool = clothing_pool if clothing_pool else list(CLOTHING_SETS.keys())
    valid = [k for k in pool if k in CLOTHING_SETS]
    if not valid:
        valid = list(CLOTHING_SETS.keys())

    clothing_key = random.choice(valid)
    clothing_tags = CLOTHING_SETS[clothing_key]

    underwear_key = random.choice(list(UNDERWEAR_SETS.keys()))
    underwear_tags = UNDERWEAR_SETS[underwear_key]

    return {
        "clothing_key": clothing_key,
        "clothing_tags": clothing_tags,
        "underwear_key": underwear_key,
        "underwear_tags": underwear_tags,
    }


def roll_character(location: str, clothing_pool: list[str] | None = None) -> dict:
    """Random composition of a full character trait set. Seed data for Grok."""
    appearance = roll_appearance()
    body = roll_body()
    clothing = roll_clothing(location, clothing_pool=clothing_pool)

    # danbooru_tags — store only the character-fixed parts
    danbooru_tags = {
        "appearance": dedup_tags(appearance["appearance_tags"]),
        "body": dedup_tags(body["body_tags"]),
        "clothing": dedup_tags(clothing["clothing_tags"]),
        "underwear": dedup_tags(clothing["underwear_tags"]),
    }

    return {
        # Raw tags (per part)
        "appearance": appearance,
        "body": body,
        "clothing": clothing,
        # Identity-fixed tags (situational/expression tags are chosen by Grok)
        "danbooru_tags": danbooru_tags,
    }


# ─────────────────────────────────────────────────────────────────────
# SFW scene-type pool — loaded from config/sfw_scenes.json.
# Python pre-selects a scene and passes it to Grok as seed data.
# Schema and maintenance rules live in the config/sfw_scenes.json header.
# ─────────────────────────────────────────────────────────────────────

_SFW_SCENES_PATH = Path(__file__).parent.parent / "config" / "sfw_scenes.json"


def _load_sfw_scenes() -> list[dict]:
    """Load config/sfw_scenes.json. Keys with `_` prefix are docs/templates and are skipped.

    Each returned dict includes a `key` field (the object key copied back into
    the value) — keeps API compatibility with the previous Python literal layout.
    """
    try:
        with open(_SFW_SCENES_PATH) as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.error("SFW_SCENES file missing: %s", _SFW_SCENES_PATH)
        return []
    except json.JSONDecodeError as e:
        logger.error("SFW_SCENES JSON parse failed (%s): %s", _SFW_SCENES_PATH, e)
        return []

    scenes: list[dict] = []
    for key, val in raw.items():
        if key.startswith("_"):
            continue
        if not isinstance(val, dict):
            logger.warning("SFW_SCENES[%s]: not a dict — skipping", key)
            continue
        entry = dict(val)
        entry["key"] = key
        # Validate required fields (lenient — fill missing ones with empty values)
        entry.setdefault("label", key)
        entry.setdefault("person_tags", "1girl, solo")
        entry.setdefault("pose_pool", [])
        entry.setdefault("camera_pool", [])
        entry.setdefault("location_pool", [])
        entry.setdefault("activity_tags", "")
        entry.setdefault("expression_hint", "")
        entry.setdefault("notes", "")
        scenes.append(entry)
    return scenes


SFW_SCENES: list[dict] = _load_sfw_scenes()


_FORCED_SFW_SCENE: str | None = os.getenv("FORCE_SFW_SCENE") or None


def list_sfw_scene_keys() -> list[str]:
    """Return every key in SFW_SCENES."""
    return [s["key"] for s in SFW_SCENES]


def set_forced_sfw_scene(key: str | None) -> tuple[bool, str]:
    """Override the SFW scene at runtime. Pass None or "" to clear.

    Returns: (ok, message) — for an invalid key, (False, reason).
    """
    global _FORCED_SFW_SCENE
    if not key:
        _FORCED_SFW_SCENE = None
        return True, "SFW scene override cleared — random selection restored"
    key = key.strip()
    valid = list_sfw_scene_keys()
    if key not in valid:
        return False, f"Unknown SFW scene key '{key}'. Valid: {', '.join(valid)}"
    _FORCED_SFW_SCENE = key
    return True, f"SFW scene forced to '{key}'"


def get_forced_sfw_scene() -> str | None:
    """Return the current SFW override key (None if not set)."""
    return _FORCED_SFW_SCENE


def roll_sfw_scene(weights: list[float] | None = None) -> dict:
    """Pick one SFW scene uniformly at random (or with weights). Returns a deep copy.

    - When `_FORCED_SFW_SCENE` is set (via env `FORCE_SFW_SCENE` or
      `set_forced_sfw_scene()`), skip random and return that scene — used for testing.
    """
    import copy
    if _FORCED_SFW_SCENE:
        forced = next((s for s in SFW_SCENES if s["key"] == _FORCED_SFW_SCENE), None)
        if forced:
            return copy.deepcopy(forced)
    chosen = random.choices(SFW_SCENES, weights=weights, k=1)[0] if weights else random.choice(SFW_SCENES)
    return copy.deepcopy(chosen)
