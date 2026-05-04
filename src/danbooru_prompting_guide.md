# Danbooru Tagging Guide (SFW)
## For Illustrious-Based Models (oneObsession) + Visual Novel Sprite Generation

Compiled research from Civitai guides, Danbooru wiki, and community best practices.
Target model: oneObsession (Illustrious-XL based, Danbooru-trained, v-prediction).

**Scope**: SFW-only Danbooru tagging reference for the AI Chat Manager
project. Only `rating:safe` (a.k.a. `rating:general`) is discussed. The
companion external prompt file `config/grok_prompts.json` enforces the
same SFW boundary on the Grok-side rule set.

---

## 1. Core Tag Structure & Order

Illustrious-based models are trained on Danbooru tag captions. Tags earlier in the prompt have stronger influence; later tags become progressively diluted. The model has a 248-token limit without layering (SDXL batches at 75 tokens per chunk).

### Recommended Tag Order

```
[person_count], [character_name], [rating], [physical_features], [clothing],
[expression], [pose/composition], [scene/background], [style/effects],
[quality_tags], [year_modifier]
```

**Detailed breakdown:**

| Position | Category | Examples |
|----------|----------|---------|
| 1 | Person count | `1girl`, `1boy`, `2girls`, `solo` |
| 2 | Character name | `seo jinhyuk`, `yoon siha` (if using character LoRA) |
| 3 | Rating | `rating:safe` / `rating:general` (only SFW tier supported in this fork) |
| 4 | Physical features | Hair, eyes, face, body type |
| 5 | Clothing/outfit | All garment tags (full outfits — never partial / undress states) |
| 6 | Expression | Facial expression tags |
| 7 | Pose/composition | Framing, camera angle, pose |
| 8 | Scene/background | Location + concrete props only |
| 9 | Style/effects | Artist style, medium, visual effects |
| 10 | Quality tags | `masterpiece`, `best quality` |
| 11 | Year modifier | `newest`, `recent` |

**Alternative order** (from Arctenox guide): artist tag first, then 1girl/1boy, character description, items, expressions, scene, effects, quality prompts.

**Key principle**: Place the most important elements first. For VN sprites, character appearance tags should come early since that's the critical content.

### Syntax Rules

- **Comma-separated**: Every tag must be separated by commas
- **Lowercase only**: `masterpiece` not `Masterpiece`
- **Underscores optional**: `long_hair` and `long hair` both work, but some special tags need underscores (e.g., `+_+`)
- **Escape parentheses**: Tags with parentheses like `vex_(lol)` must be escaped as `vex \(lol\)` since parentheses are used for weighting
- **Tag count**: Optimal range is 20-40 tags for SDXL-based models

---

## 2. Quality Tags

### Quality Tag Hierarchy (Danbooru Training Scores)

| Tag | Score Percentile | Usage |
|-----|-----------------|-------|
| `masterpiece` | 100% | Always include in positive |
| `best quality` | 92%+ | Always include in positive |
| `amazing quality` | ~95% | Alternative/supplement |
| `good quality` | 92% | Optional supplement |
| `normal quality` | 60% | Avoid in positive |
| `average quality` | 60% | Avoid in positive |
| `bad quality` | 20% | Use in negative |
| `worst quality` | 8% | Always include in negative |
| `low quality` | ~15% | Use in negative |

### Recommended Positive Quality Block

```
masterpiece, best quality, very aesthetic, absurdres, newest
```

### For oneObsession (v-pred) Specifically

From model documentation:
```
Positive: masterpiece, best quality, good quality, newest
Negative: lowres, worst quality, bad quality, bad anatomy, sketch, jpeg artifacts, signature, watermark, old, oldest
```

### Important Notes

- **`absurdres` / `highres`**: Debated effectiveness. The Illustrious prompting guide says these "won't make your gen better" and any improvement is random. However, many users report benefits. Place at end of prompt if used.
- **Score tags (`score_9`, etc.)**: Do NOT work on Illustrious. Those are Pony Diffusion only.
- **Cargo cult tags**: `8k`, `4k`, `hdr`, `high quality`, `detailed`, `many` are NOT recognized Danbooru tags. Do not use them.
- **`lowres`**: Actively harmful in positive prompt. Will degrade quality.
- **`very aesthetic`**: Recognized by oneObsession; generally improves output aesthetics.

---

## 3. Rating Policy (SFW Only)

This fork supports only the safe / general Danbooru rating tier.

| Tier | Policy in this fork |
|------|--------------------|
| `rating:safe` / `rating:general` | **Only allowed tier** — every prompt assembled by this fork must be safe-tier |
| `rating:sensitive` | Not used by the fork's prompt pipeline |
| `rating:questionable` | Not used in the SFW fork — never emitted |
| `rating:explicit` | Not used in the SFW fork — never emitted; treated as a hard violation |

### Vulgar / Anatomy AVOID list

Even in SFW prompts, never let the following families of tags leak into the positive
prompt. They must always be suppressed at the prompt-assembly layer (and most also
belong in the negative prompt — see Section 9):

- Sex-act / penetration / coupling vocab (e.g. `sex`, `oral`, `fellatio`, `vaginal`,
  `mating`, `gangbang`, etc.)
- Body-fluid vocab (`cum`, `creampie`, `pussy_juice`, `squirting`, etc.)
- Explicit anatomy vocab (`pussy`, `nipples`, `clitoris`, `anus`, `pubic_hair`,
  detailed breast / genital descriptors)
- Undress / exposure-state tags (`nude`, `naked`, `topless`, `bottomless`,
  `no_panties`, `undressing`, lingerie-only states)
- Climax / arousal-face tags (`ahegao`, `orgasm`, `rolling_eyes` paired with
  `tongue_out`, `heart-shaped_pupils` in arousal context)

This guard mirrors the "Vulgar anatomy — AVOID in motion_prompt" guard in
`src/wan_i2v_prompting_guide.md`. The fork's Grok prompt rules (in
`config/grok_prompts.json`) enforce the same allow-list at generation time.

---

## 4. Character Description Tags

### Face Features

| Feature | Tags |
|---------|------|
| Face shape | `round face`, `heart-shaped face`, `thin face` |
| Jaw | `sharp jaw`, `pointed chin` |
| Nose | `small nose`, `button nose`, `dot nose` |
| Lips | `thin lips`, `pouty lips`, `parted lips` |
| Facial hair | `stubble`, `beard`, `goatee`, `mustache` |
| Skin tone | `pale skin`, `dark skin`, `tan`, `light brown skin` |
| Scars | `scar`, `facial scar`, `scar on cheek`, `scar across eye` |
| Glasses | `glasses`, `round eyewear`, `semi-rimless eyewear`, `rimless eyewear` |

### Hair — Color

`black hair`, `brown hair`, `blonde hair`, `silver hair`, `grey hair`, `white hair`, `red hair`, `blue hair`, `green hair`, `pink hair`, `purple hair`, `orange hair`, `platinum blonde hair`, `light brown hair`, `dark blue hair`, `two-tone hair`, `multicolored hair`, `gradient hair`, `streaked hair`

### Hair — Length

`very short hair`, `short hair`, `medium hair`, `long hair`, `very long hair`, `absurdly long hair`

### Hair — Style

| Category | Tags |
|----------|------|
| Basic | `straight hair`, `wavy hair`, `curly hair`, `messy hair`, `shiny hair` |
| Ponytails | `ponytail`, `high ponytail`, `low ponytail`, `side ponytail`, `short ponytail`, `folded ponytail`, `split ponytail` |
| Twintails | `twintails`, `low twintails`, `short twintails`, `uneven twintails` |
| Braids | `braid`, `twin braids`, `french braid`, `side braid`, `braided ponytail` |
| Buns | `hair bun`, `double bun`, `braided bun`, `low bun`, `side bun` |
| Cuts | `bob cut`, `hime cut`, `wolf cut`, `pixie cut`, `crew cut`, `bowl cut`, `undercut` |
| Drills | `drill hair`, `twin drills`, `side drill` |
| Other | `sidelocks`, `ahoge`, `hair over one eye`, `hair between eyes`, `swept bangs` |

### Hair — Bangs

`blunt bangs`, `swept bangs`, `side bangs`, `parted bangs`, `curtained hair`, `long bangs`, `short bangs`, `arched bangs`, `asymmetrical bangs`, `choppy bangs`, `diagonal bangs`, `wispy bangs`, `hair over eyes`, `hair between eyes`, `bangs pinned back`

### Eyes

| Feature | Tags |
|---------|------|
| Color | `blue eyes`, `red eyes`, `green eyes`, `brown eyes`, `black eyes`, `grey eyes`, `purple eyes`, `yellow eyes`, `amber eyes`, `golden eyes`, `heterochromia` |
| Shape/Style | `narrow eyes`, `tsurime` (sharp upturned), `tareme` (droopy gentle), `half-closed eyes`, `wide eyes`, `slit pupils`, `constricted pupils` |
| Special | `glowing eyes`, `empty eyes`, `teary eyes`, `sleepy eyes`, `sparkling eyes`, `cross-eyed` |

### Body Type

| Tag | Description |
|-----|-------------|
| `slim` | Slender build |
| `petite` | Small frame |
| `tall` | Tall character |
| `short` | Short character |
| `muscular` | Bulky, muscular physique (from extensive training) |
| `toned` | Athletic build, not overly bulky |
| `curvy` | Curvy figure |
| `plump` | Heavier build |
| `broad shoulders` | Wide shoulders |
| `narrow waist` | Slim waist |
| `abs` | Visible abdominal muscles |
| `collarbone` | Visible collarbone (suggests slim/fit build) |

**Important**: Separate compound descriptions into individual tags. Instead of "short black pleated skirt", use: `skirt, black skirt, short skirt, pleated skirt`. This applies to character features too.

---

## 5. Expression Tags

### Complete Expression Reference

#### Basic Emotions
| Expression | Primary Tag(s) | Notes |
|-----------|----------------|-------|
| Neutral | `expressionless`, `serious` | Default calm face |
| Happy | `smile`, `happy` | General happiness |
| Sad | `sad`, `depressed`, `frown` | General sadness |
| Angry | `angry` | General anger |
| Surprised | `surprised`, `wide-eyed` | Shock/surprise |
| Scared | `scared`, `panicking`, `worried` | Fear |
| Disgusted | `disgust` | Revulsion |
| Bored | `bored` | Disinterest |

#### Smile Variants
`smile`, `light smile`, `grin`, `evil smile`, `crazy smile`, `sad smile`, `forced smile`, `smirk`, `smug`, `:D`

#### Mouth States
`open mouth`, `closed mouth`, `parted lips`, `clenched teeth`, `biting own lip`, `:o`, `chestnut mouth`, `wavy mouth`

#### Eye States
`closed eyes`, `half-closed eyes`, `one eye closed`, `wide-eyed`, `narrowed eyes`, `rolling eyes`

#### Blush Variants
`blush`, `light blush`, `full-face blush`, `nose blush`, `blush stickers`

#### Complex States
`tears`, `crying`, `streaming tears`, `teardrop`, `pout`, `furrowed brow`, `raised eyebrow`, `v-shaped eyebrows`, `nosebleed`, `sigh`, `nervous`, `flustered`, `embarrassed`, `frustrated`, `exhausted`, `sleepy`, `thinking`, `pensive`, `lonely`, `sulking`, `disdain`, `envy`, `determined`, `excited`, `annoyed`, `confused`, `grimace`, `wince`, `pain`, `despair`, `guilt`

#### Emotes (Stylized Expressions)
`:3`, `;3`, `x3`, `0w0`, `uwu`, `:p`, `;p`, `:q`, `>:)`, `>:(`, `:T`, `:/`, `:|`, `:c`, `:<`, `:>`, `:o`, `o_o`, `0_0`, `._.`

### Multi-Tag Expression Combinations for VN Sprites

These proven combinations produce nuanced expressions (from Civitai expression guide):

| Target Expression | Tag Combination |
|------------------|-----------------|
| Calm/Normal | `expressionless, serious` |
| Slight Smile | `expressionless, smug` |
| Talking (happy) | `open mouth, smug` |
| Satisfied | `bored, smug` |
| Reassuring | `smug, raised eyebrows` |
| Frowning | `bored, determined` |
| Sad | `depressed` |
| Sad (talking) | `depressed, open mouth` |
| Angry | `angry` |
| Angry (talking) | `angry, open mouth` |
| Mocking | `angry, laughing` |
| Pouty | `pout` |
| Surprised (mild) | `surprised, closed mouth` |
| Surprised (strong) | `surprised, open mouth` |
| Disinterested | `bored` |
| Disgusted | `disgust` |
| Happy/Laughing | `laughing, closed eyes` |
| Humiliated rage | `angry, laughing, closed eyes` |

---

## 6. Pose & Composition Tags

### Framing (CRITICAL for VN Sprites)

| Tag | What It Shows | VN Use |
|-----|---------------|--------|
| `portrait` | Head and shoulders only | Close-up dialogue |
| `upper body` | Head to waist | **Most common for VN sprites** |
| `cowboy shot` | Head to mid-thigh | **Standard VN sprite framing** |
| `full body` | Entire body including feet | Full character reveal |
| `close-up` | Very tight framing | Detail shots |
| `wide shot` | Character small in frame | Establishing shots |
| `lower body` | Waist down | Rarely used for sprites |
| `head out of frame` | Body without head | Never use for sprites |
| `feet out of frame` | Full body minus feet | Variant of cowboy shot |

### Camera Angles

| Tag | Description |
|-----|-------------|
| `straight-on` | **Default for VN sprites** - direct front view |
| `from side` | Side view |
| `from above` | Looking down at character |
| `from below` | Looking up at character |
| `from behind` | Rear view |
| `dutch angle` | Tilted camera |
| `three quarter view` | 3/4 angle |
| `profile` | Pure side profile |

### Gaze Direction

| Tag | Description |
|-----|-------------|
| `looking at viewer` | **Essential for VN sprites** - character looks at camera/player |
| `looking away` | Averted gaze |
| `looking back` | Turned away but looking back |
| `looking down` | Downcast eyes |
| `looking up` | Eyes directed upward |
| `sideways glance` | Side-eye |
| `facing viewer` | Body oriented toward viewer |

### Body Poses

`standing`, `sitting`, `walking`, `running`, `lying down`, `leaning forward`, `leaning back`, `arms crossed`, `arms at sides`, `hand on hip`, `hands in pockets`, `arms behind back`, `arms behind head`, `hand on own chin`, `hand on own chest`, `head tilt`, `contrapposto`

### Recommended Combo for VN Sprites

```
upper body, straight-on, looking at viewer
```
or
```
cowboy shot, straight-on, looking at viewer
```

---

## 7. Outfit/Clothing Tags

### Tag Decomposition Principle

**CRITICAL**: Break complex outfits into component tags.

Bad: `man in dark business suit with white shirt and tie`
Good: `suit, black suit, dress shirt, white shirt, necktie, black necktie`

### SFW Fork Rule — Full Outfits Only

This fork only emits **complete outfit sets**. Lingerie-only / underwear-only /
exposed-state / partial-undress combinations are not used. When tagging a clothed
character, always include a coherent set covering upper body + lower body (or a single
full-body garment such as `dress`, `kimono`, `jumpsuit`). Do not emit `panties` /
`bra` / `lingerie` / `thighhighs` as a standalone wardrobe — they may only appear
**under** a full-coverage outfit (e.g. `thighhighs` under a `skirt`), and never as the
visible clothing layer.

### Common Outfit Components

#### Upper Body
`shirt`, `dress shirt`, `collared shirt`, `t-shirt`, `blouse`, `sweater`, `turtleneck`, `cardigan`, `hoodie`, `tank top`, `vest`, `waistcoat`, `jacket`, `blazer`, `coat`, `long coat`, `trench coat`, `leather jacket`, `denim jacket`, `windbreaker`, `parka`, `crop top`, `off-shoulder shirt`

#### Lower Body
`pants`, `trousers`, `jeans`, `shorts`, `skirt`, `miniskirt`, `long skirt`, `pleated skirt`, `pencil skirt`, `cargo pants`, `sweatpants`

#### Full Body
`dress`, `jumpsuit`, `overalls`, `kimono`, `yukata`, `hanfu`, `cheongsam`

#### Formal/Work
`suit`, `business suit`, `tuxedo`, `necktie`, `bowtie`, `dress shirt`, `formal`, `office lady`, `salaryman`

#### Outerwear
`coat`, `jacket`, `cape`, `cloak`, `scarf`, `shawl`, `poncho`

#### Accessories
`belt`, `watch`, `necklace`, `ring`, `bracelet`, `earrings`, `hair ribbon`, `hair clip`, `hairband`, `hat`, `beret`, `cap`, `badge`, `lanyard`, `bag`, `backpack`

#### Footwear
`shoes`, `boots`, `sneakers`, `loafers`, `high heels`, `sandals`, `slippers`, `socks`, `knee-high socks`, `thigh-high socks`

#### Uniforms
`school uniform`, `serafuku` (sailor uniform), `military uniform`, `police uniform`, `nurse`, `lab coat`, `chef uniform`, `maid`, `gym uniform`

#### Outfit examples (per role / archetype)

| Archetype | Key Outfit Tags |
|-----------|----------------|
| Office worker (jacket) | `1boy, jacket, dark jacket, collared shirt, necktie, pants, dark pants` |
| Office worker (shirt) | `1boy, dress shirt, white shirt, rolled up sleeves, pants` |
| Florist (apron) | `1girl, apron, green apron, long sleeves, casual` |
| Day-out / casual | `1girl, coat, long coat, casual, dress` |
| Spectacled professional | `1boy, glasses, semi-rimless eyewear, suit, dress shirt, necktie` |
| Researcher / lab | `1girl, lab coat, white coat, professional` |
| Formal executive | `1boy, suit, dress shirt, necktie, formal` |

### Color Specification

Format: `[color] [item]` — e.g., `black jacket`, `white shirt`, `blue necktie`, `grey pants`

Colors work intuitively. Common ones: `black`, `white`, `grey`, `dark grey`, `brown`, `navy blue`, `dark blue`, `red`, `green`, `beige`, `khaki`, `cream`

---

## 8. Background Tags

### For VN Sprite Generation (Transparent/Simple)

| Tag | Result | Use Case |
|-----|--------|----------|
| `transparent background` | **Checkered/alpha transparency** | **Primary choice for VN sprites** |
| `simple background` | Clean solid color | Sprite extraction |
| `white background` | Pure white | Easy to key out |
| `grey background` | Neutral grey | Alternative for extraction |
| `green background` | Green screen style | Chroma key extraction |

### For CG/Scene Generation

#### Solid Colors
`aqua background`, `black background`, `blue background`, `brown background`, `green background`, `grey background`, `orange background`, `pink background`, `purple background`, `red background`, `white background`, `yellow background`

#### Patterns
`gradient background`, `two-tone background`, `striped background`, `checkered background`, `polka dot background`, `argyle background`

#### Descriptive
`abstract background`, `blurry background`, `bright background`, `dark background`, `detailed background`

#### Scene Backgrounds
`indoors`, `outdoors`, `night`, `day`, `rain`, `snow`, `cityscape`, `street`, `alley`, `office`, `room`, `bedroom`, `kitchen`, `hospital`, `police station`, `cafe`, `park`, `rooftop`, `cemetery`

### VN Sprite Background Best Practice

```
transparent background
```

If transparent doesn't work well with the model/workflow, use:
```
simple background, white background
```
Then remove the background in post-processing.

---

## 9. Negative Prompt Best Practices

### Universal Negative Prompt Template (Illustrious/oneObsession)

```
lowres, worst quality, bad quality, bad anatomy, bad hands, extra digits,
missing fingers, extra fingers, fused fingers, poorly drawn hands,
poorly drawn face, mutation, deformed, blurry, ugly, jpeg artifacts,
signature, watermark, username, text, error, extra limbs, missing limbs,
extra arms, extra legs, fused body parts
```

### SFW-Heavy Negative (recommended for this fork)

In addition to the universal block above, this fork prepends an explicit SFW guard so
the diffusion sampler is actively pushed away from explicit / undress / arousal
imagery even if the positive prompt is incomplete. This is intentional — the listed
tags below are the things we want to **suppress** in the output:

```
nsfw, rating:explicit, rating:questionable, nude, naked, topless, bottomless,
undressing, undressed, no_panties, no_bra, lingerie, see-through,
nipples, pussy, anus, pubic_hair, cum, pussy_juice, sex, oral, fellatio,
penetration, mating, ahegao, orgasm, squirting
```

This block is the SFW negative-prompt safety net described in `CLAUDE.md` and parallels
the comparable AVOID list in `src/wan_i2v_prompting_guide.md`. The
`embedding:illustrious/lazy-nsfw` token is also prepended as the very first negative
embedding by `src/comfyui.py`.

### Extended Negative (for cleaner sprites)

```
lowres, worst quality, bad quality, bad anatomy, bad hands, extra digits,
missing fingers, extra fingers, fused fingers, poorly drawn hands,
poorly drawn face, mutation, deformed, blurry, ugly, jpeg artifacts,
signature, watermark, username, text, error, extra limbs, missing limbs,
extra arms, extra legs, fused body parts, multiple views, comic, 4koma,
monochrome, greyscale, sketch, unfinished, displeasing, oldest, early,
chromatic aberration, artistic error, scan
```

### Situational Additions

| Issue | Add to Negative |
|-------|----------------|
| Getting B&W images | `monochrome, greyscale` |
| Getting comic panels | `comic, 4koma, 2koma, multiple views` |
| Text/watermarks appearing | `text, watermark, signature, translation request, patreon logo` |
| Underage appearance | `loli, shota, child, aged down` |
| Too realistic | (for anime) `photo, realistic, photorealistic` |
| Multiple characters | `multiple girls, multiple boys, 2girls, crowd` |

### Important Principles

1. **Less is more**: Excessive negative prompts create unpredictable results. Focus on strong positive prompts instead.
2. **Don't negate what you didn't prompt**: Only add negatives for issues you actually encounter.
3. **Quality negatives are essential**: `worst quality, low quality` should almost always be included.
4. **SFW guard is non-negotiable in this fork**: the SFW-heavy negative block above is always included regardless of the positive prompt's apparent risk.
5. **Model-specific**: Test your specific model. oneObsession may need different negatives than base Illustrious.

---

## 10. Common Mistakes to Avoid

### 1. Using Natural Language Instead of Tags

**BAD**: `a beautiful young woman with long flowing black hair wearing a dark business suit standing in the rain`

**GOOD**: `1girl, solo, beautiful, long hair, black hair, flowing hair, suit, dark suit, standing, rain, outdoors`

Danbooru-trained models understand discrete tags, not sentences. Natural language wastes tokens and produces inconsistent results.

### 2. Using Unrecognized Tags

**BAD**: `8k, 4k, hdr, high quality, detailed, ultra detailed, score_9, best score`

These are NOT Danbooru tags. The model doesn't understand them. Verify tags exist on [danbooru.donmai.us/tags](https://danbooru.donmai.us/tags).

**Rule of thumb**: Tags with fewer than ~100 Danbooru posts likely won't work. Tags with fewer than ~20 posts definitely won't.

### 3. Wrong Parentheses Handling

**BAD**: `astolfo (fate)` — This applies emphasis weighting to "fate"

**GOOD**: `astolfo \(fate\)` — This properly escapes the parentheses

### 4. Compound Descriptions Instead of Decomposed Tags

**BAD**: `short black pleated skirt`

**GOOD**: `skirt, black skirt, short skirt, pleated skirt`

Each attribute should be its own tag.

### 5. Too Many Tags (Over-Tagging)

50+ tags overwhelms SDXL models. Stay within 20-40 tags. Prioritize what matters.

### 6. Conflicting Tags

- `outdoors` + `indoors` in the same prompt
- `day` + `night`
- `smile` + `frown` (unless going for a specific complex expression)
- `long hair` + `short hair`

### 7. Wrong Name Order for Characters

Danbooru uses the name order as shown on the site. For Japanese media, this is typically Japanese order (family name first): `kinoshita hideyoshi`, not `hideyoshi kinoshita`.

### 8. Using Underscores in Prompts Unnecessarily

Underscores are Danbooru's search syntax, not meaningful tokens. `long_hair` and `long hair` work the same in prompts. Some people argue underscores waste tokens; others say it doesn't matter. Either works, but be aware special tags like `+_+` need the underscore.

### 9. Using Capitalization

All Danbooru tags are lowercase. Don't capitalize.

### 10. CFG Too High

Maximum 6 CFG for Illustrious-based models. Values above risk "overbaking" (oversaturation, artifacts). Start at 3, go up to ~5.5 max. oneObsession recommends using Rescale CFG up to 0.7 for v-pred.

---

## 11. Solo Character Enforcement

For VN sprites, you almost always want exactly one character. Use this combination:

### Positive Prompt

```
1boy, solo, ...  (for male characters)
1girl, solo, ... (for female characters)
```

**Both tags are needed**:
- `1boy` / `1girl` specifies the count
- `solo` reinforces that only one character should appear

### Negative Prompt

Add to prevent extra characters:
```
multiple boys, multiple girls, 2boys, 2girls, crowd, group, everyone
```

### Additional Reinforcement

- Use `looking at viewer` — this strongly implies a single subject
- Use `upper body` or `cowboy shot` — tighter framing reduces chance of extra characters
- Avoid tags that imply interaction: `holding hands`, `hug`, `couple`, `duo`

---

## 12. Eye Color Control

### Basic Eye Color Tags

`blue eyes`, `red eyes`, `green eyes`, `brown eyes`, `black eyes`, `grey eyes`, `purple eyes`, `yellow eyes`, `amber eyes`, `golden eyes`, `pink eyes`, `aqua eyes`, `orange eyes`, `silver eyes`

### Reliability Tips

1. **Place early in prompt**: Eye color should be in the physical features section, near the beginning
2. **Use emphasis if needed**: `(green eyes:1.2)` for stronger adherence
3. **Avoid conflicting character tags**: If using a known character name, their canonical eye color may override your specification
4. **Add to negative**: If getting wrong eye color, add the wrong color to negatives: e.g., negative `blue eyes` if you want green
5. **Heterochromia**: Use `heterochromia` plus specific colors: `heterochromia, blue eyes, red eyes`
6. **Special eye types**: `glowing eyes`, `empty eyes`, `slit pupils`, `sparkling eyes`, `teary eyes`

### Per-character notes

For each character, set the eye-color tag in
`persona/charNN.json:image_prompt_prefix` so it's applied to every
render. If the character wears glasses, the `glasses` tag interacts
with eye rendering — verify a few generations.

### Known Issues

- Eye color can be inconsistent across generations even with the same prompt
- Character LoRAs or strong artist styles may override eye color tags
- With IPAdapter FaceID, the reference image's eye color may conflict with tags (see Section 14)

---

## 13. Age/Maturity Control

### Danbooru Age-Related Tags

| Tag | Danbooru Definition |
|-----|-------------------|
| `mature female` | Middle-aged or older woman with visual age markers (wrinkles, curvier body). Aliases: `mature`, `mature woman`, `milf` |
| `mature male` | Middle-aged or older man with visual age markers |
| `old woman` | Elderly female |
| `old man` | Elderly male |
| `boy` | Young male |
| `girl` | Young female |
| `child` | Very young character |
| `aged up` | Character depicted older than canonical age |
| `aged down` | Character depicted younger than canonical age |

### Making Characters Look Adult/Appropriate Age

For adult characters (20s-30s range, most of this project's cast):

**Positive tags to add:**
```
adult, mature, tall
```

**Physical indicators of maturity:**
```
toned, collarbone, narrow eyes, sharp jaw, stubble (for men),
facial hair (for older men), wrinkles (for 40s+)
```

**Negative tags to prevent young appearance:**
```
loli, shota, child, aged down, baby face
```

### Age-range strategies

| Age range | Strategy |
|-----------|----------|
| Child (~10) | `1boy/1girl, child, young, short` — let the model default to young-looking |
| 20s | `1girl/1boy, adult` + mature physical features like `toned`, `collarbone` |
| 30s | `1boy, adult, mature male` + `stubble` or `facial hair` if appropriate |
| 40s | `1girl, adult, mature female` + subtle age markers |
| 50s+ | `1boy, mature male, old` + `grey hair`, `wrinkles` if appropriate |

### Important Notes

- Anime style inherently trends young. You need to actively push toward maturity for older characters.
- `mature female` on Danbooru implies visual markers: slight wrinkles, curvier body, NOT just being a mother
- For male characters in their 30s: `stubble`, `facial hair`, `sharp features`, `narrow eyes` help convey age
- For characters in their 40s-50s: `grey hair`, `wrinkles`, `tired eyes` are effective
- Adding character-specific physical markers (scars, tired eyes, etc.) helps more than generic age tags

---

## 14. IPAdapter FaceID Considerations

### How IPAdapter FaceID Interacts with Tags

When using IPAdapter FaceID for character consistency:

1. **FaceID controls the face; text prompt controls everything else**
2. The face reference image takes priority over face-related text tags
3. Text prompt still controls: outfit, pose, expression (partially), background, composition

### Critical Rules

#### DO NOT describe the face in text prompts when using FaceID
Face descriptions in prompts conflict with reference guidance and produce weird artifacts. Let the reference image handle facial features.

**With FaceID, REMOVE these from positive prompt:**
- Specific eye color tags (unless reinforcing reference)
- Face shape tags
- Nose/lip descriptions
- Specific facial feature tags

**KEEP in positive prompt:**
- Hair tags (color, length, style) — FaceID focuses on face, not hair
- Expression tags — these modify the face generated from reference
- Outfit tags
- Pose/composition tags
- Quality tags

#### Weight Settings

| Weight | Effect |
|--------|--------|
| 1.0 | Default — strong face matching, may override prompt |
| 0.8 | **Recommended starting point** — good balance |
| 0.7-0.75 | More flexibility for prompt, weaker face match |
| 0.6 | Weak face influence, mostly prompt-driven |
| 1.2+ | Very strong face match, stiff/unnatural results |

**General rule**: Lower weight to at least 0.8 and increase step count for best results.

#### Weight Type (IPAdapter Advanced node)

Change `weight_type` to increase prompt adherence when face matching is too dominant. Experiment with available options in the Advanced node.

#### Reference Image Quality

- Face must be clearly visible (no sunglasses, heavy shadows, hair covering face)
- Minimum 512x512 in face region
- Square images with centered face work best
- Bad reference = bad results. No settings can fix poor inputs.
- The CLIP vision model resizes reference to 224x224 with center crop — keep face centered

### Workflow for VN Sprites with FaceID

```
1. Generate initial character reference (without FaceID) using full tag prompt
2. Select best face result as reference image
3. For subsequent sprites, use FaceID with:
   - Reference image for face consistency
   - Reduced tag prompt (remove face description tags)
   - Keep: hair, expression, outfit, pose, composition, quality
   - Weight: 0.75-0.85
   - Increased steps: 24-30
```

### Expression Changes with FaceID

Expression tags still work with FaceID but may be partially overridden. For strong expression changes:
- Increase expression tag weight: `(angry:1.3)`
- Slightly lower FaceID weight: 0.7
- Expression tags and FaceID face features will blend

---

## 15. Complete VN Sprite Prompt Template

### Base Template

```
Positive:
1boy, solo, [character_specific_tags], [hair_color] hair, [hair_style],
[eye_color] eyes, [expression_tags], [outfit_tags],
upper body, straight-on, looking at viewer, simple background,
white background, masterpiece, best quality, newest

Negative:
lowres, worst quality, bad quality, bad anatomy, bad hands,
extra digits, missing fingers, extra fingers, blurry, ugly,
signature, watermark, text, multiple boys, multiple girls,
monochrome, greyscale, comic, multiple views
```

### Example: male office worker (jacket + brooding expression)

```
Positive:
1boy, solo, adult, mature male, short hair, black hair, swept bangs,
dark eyes, narrow eyes, tired eyes, stubble,
furrowed brow, serious, frown,
jacket, dark jacket, collared shirt, necktie, pants,
upper body, straight-on, looking at viewer,
simple background, white background,
masterpiece, best quality, newest

Negative:
lowres, worst quality, bad quality, bad anatomy, bad hands,
extra digits, blurry, ugly, signature, watermark, text,
multiple boys, monochrome, greyscale, comic, multiple views,
child, shota, loli
```

### Example: female florist (apron + soft smile)

```
Positive:
1girl, solo, adult, long hair, [hair_color] hair, [hair_style],
[eye_color] eyes,
light smile, gentle expression, head tilt,
apron, green apron, long sleeves, casual clothes,
upper body, straight-on, looking at viewer,
simple background, white background,
masterpiece, best quality, newest

Negative:
lowres, worst quality, bad quality, bad anatomy, bad hands,
extra digits, blurry, ugly, signature, watermark, text,
multiple girls, monochrome, greyscale, comic, multiple views,
child, loli
```

---

## 16. Quick Reference Card

### Minimum Viable Sprite Prompt
```
1[boy/girl], solo, [hair], [eyes], [expression], [outfit],
upper body, looking at viewer, simple background, white background,
masterpiece, best quality
```

### Tag Weight Syntax
- `(tag:1.2)` = 20% more emphasis
- `(tag:1.5)` = 50% more emphasis
- `(tag:0.7)` = 30% less emphasis
- `((tag))` = double emphasis (equivalent to ~1.21x)

### oneObsession Recommended Settings
- **CFG**: 3-5.5 (use Rescale CFG up to 0.7 for v-pred)
- **Sampler**: Euler A
- **Steps**: 20-30
- **Resolution**: 1024x1024 or 832x1216 (portrait)
- **Clip skip**: 2

### Tag Verification
Always verify tags exist: [danbooru.donmai.us/tags](https://danbooru.donmai.us/tags)

### Cross-References (in this fork)

- `config/grok_prompts.json` — Grok-side externalized SFW Danbooru rule set (LLM emits prompts that obey the Section 3 rating policy and the Section 9 SFW negative guard).
- `src/wan_i2v_prompting_guide.md` — sibling SFW i2v motion-prompt guide (was `wan_nsfw_i2v_prompting_guide.md` in the original repo; renamed and stripped on fork).
- `src/comfyui.py` — embedding prefix wiring; `embedding:illustrious/lazy-nsfw` is prepended to the negative prefix as a hard SFW guard.

---

## Sources

- [Arctenox's Simple Prompt Guide for Illustrious](https://civitai.com/articles/23210/arctenoxs-simple-prompt-guide-for-illustrious)
- [Illustrious Prompting Guide v0.1](https://civitai.com/articles/10962/illustrious-prompting-guide-or-v01-or-generate-anime-art-with-ai)
- [Tips for Illustrious XL Prompting](https://civitai.com/articles/8380/tips-for-illustrious-xl-prompting-updates)
- [Obsession (Illustrious-XL) Model Page](https://civitai.com/models/820208/obsession-illustrious-xl)
- [Booru Style Tagging SDXL Anime Prompts Guide](https://droid4x.com/booru-style-tagging-sdxl-anime-prompts-guide/)
- [Camera & Focus Danbooru Tags Guide](https://civitai.com/articles/13602/camera-and-focus-danbooru-tags-guide-series-still-editing)
- [280+ Clothing Tags List](https://civitai.com/articles/6349/280-pony-diffusion-xl-recognized-clothing-list-booru-tags-sfw)
- [320+ Character Hairstyles Tags](https://civitai.com/articles/6888/320-pony-diffusion-xl-character-hairstyles-ears-wings-and-tails-booru-tags-sfw)
- [Danbooru Facial Expression Tags](https://civitai.com/articles/5492/danbooru-tags-complex-facial-expressions-for-ponyxl-autismmix)
- [Common Style Tags for Illustrious](https://civitai.com/articles/25464/common-style-tags-recognized-by-illustrious-and-other-danbooru-based-models)
- [Danbooru Wiki - Tag Group: Image Composition](https://danbooru.donmai.us/wiki_pages/tag_group:image_composition)
- [Danbooru Wiki - Tag Group: Backgrounds](https://danbooru.donmai.us/wiki_pages/tag_group:backgrounds)
- [Danbooru Wiki - Tag Group: Face Tags](https://danbooru.donmai.us/wiki_pages/tag_group:face_tags)
- [ComfyUI IPAdapter Plus (GitHub)](https://github.com/cubiq/ComfyUI_IPAdapter_plus)
- [IPAdapter FaceID Guide](https://ipadapterfaceid.com/)
- [Anime Prompting - MonAI](https://wiki.monai.art/en/tutorials/anime_prompting)
