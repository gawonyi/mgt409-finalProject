# Hand Up! — Design spec v2 (tone & manner)

Reference: `design/mockup.html` (open in Chrome) and `design/mockup.png`.
Direction: **cozy + professional**. A warm isometric pixel classroom sits like a framed picture on a calm, light-sky app. Pixel art lives **only in the scene, name tags and logo**; everything else looks like a clean work tool.

## 1. Color tokens
| Token | Hex | Role |
|---|---|---|
| `--bg` | #E6F4FB | page background (light sky) |
| `--surface` | #FFFDF7 | panels, cards, dialogue box (cream white) |
| `--line` | #C9DCE8 | borders, dividers |
| `--ink` / `--ink-2` | #1F2D45 / #5B6B82 | text / secondary text |
| `--primary` | #2F86AB | main actions (Send, Start class), links, progress |
| `--speaking` | #F2C14E | **yellow outline on whoever is speaking**, professor dialogue border |
| `--me` | #F47C7C | me: my name tag, my dialogue box, Hand Up! button, "Your turn" |
| `--ok` | #6DBE8C | hand raised (active) |
| `--warn` | #E8A13A | cost warning |

Rule: background + surface ≈ 90% of the screen. Teal only for main actions. Yellow and coral only to answer "who is speaking?" and "where am I?". Fewer accents = more professional.

## 2. Type
- Body, dialogue, evaluation: **Inter** (14–16 px, line-height 1.5).
- Logo, name tags, speaker names: **Pixelify Sans**.
- No Press Start 2P.

## 3. Shape
- Borders 2 px `--line`; radius 6 px (pills 999 px); soft shadow `0 4px 12px rgba(31,45,69,.08)`.
- Spacing on an 8 px scale (8 / 16 / 24).
- No heavy dark outlines or hard drop shadows in the UI (those belong to the pixel art only).

## 4. Classroom scene (image assets)
Stored once in `static/img/` (never generated at runtime). Preview: `design/scene_preview.png`.
| File | Content |
|---|---|
| `room.png` | our real case-room redrawn as an isometric pixel scene (U-shaped curved desks, 3 empty screens, lectern), 7 empty chairs facing the desks |
| `sprites/<name>_back.png` | students seated in a chair, seen from behind (brunette, brown, blonde, dark) |
| `sprites/<name>_front.png` | the same students from the front: used as **dialogue-box portraits** |
| `sprites/prof.png` | professor standing, facing the class |
| `sprites/hand_icon.png`, `sprites/alert_icon.png` | raised-hand icon, cold-call "!" icon |
| `layout.json` | viewport crop, chair anchor points, scales, default seating |

- Students sit **in the room's chairs, facing their desks** (back view, sprite flipped horizontally to match the chair direction). Anchor: sprite bottom-right on the chair's bottom-right point. Draw back-to-front by y.
- Show only the **viewport crop** of `room.png` (professor area + seats) so characters are large enough.
- Faces appear in the **dialogue-box portrait** (front sprite) whenever someone speaks.
- The board/screens stay empty; no text on the scene.
- **Fallback:** if images are missing, draw the code version from `design/mockup.html`.

## 5. States and motion
- **Speaking:** a 3 px yellow (`--speaking`) outline around the speaker's sprite. No talking animation, no speech bubbles.
- **Hand raised:** hand icon pops above the student's head (2-frame bob); the Hand Up! button turns `--ok`.
- **Cold call:** "!" icon above my head for 1.5 s.
- **Idle:** optional 2 px bob (`steps(2)`), may be turned off.
- **Your turn:** coral "★ Your turn" pill at the scene's top-left; the dialogue box switches to the "me" style.

## 6. Classroom layout
- Top bar: logo, course chip, session chip, turn counter.
- **Stage card** (left, wide):
  1. Scene (16:9).
  2. **RPG dialogue box** under the scene: portrait (cropped from the character sprite, 72 px) + speaker name + line. Text types out in sync with the voice; click shows the full line at once. Professor/classmates: yellow top border, cream background.
  3. **My turn:** the same box switches to coral top border and pale coral background; live speech-to-text fills the line; buttons Re-record / Send (typing mode: the line becomes a text input).
  4. Controls row: **Hand Up!** (coral, primary for the user), Pass, End class, hint "Space = raise hand · type instead"; right: cost meter + Agent trace link.
- **History drawer** (right, collapsible): full transcript; speaker color bars (yellow = professor, coral = me).
- Under 900 px width: history drawer moves below the stage.

## 7. Home and Evaluation screens
Same tokens, cards, pills and buttons. Pixel art only in small touches (logo, course card icons, character portraits next to polished lines).
