# Hand Up! — image assets and prompts

Make both images **in the same ChatGPT chat** (room first) so the style matches.
Save them to `static/img/`. They are created once, never at runtime.

| File | Required | What it is |
|---|---|---|
| `room.png` | yes | our real classroom, redrawn as an isometric pixel-art scene, with **empty** seats and an **empty** board |
| `characters.png` | yes | sprite sheet: professor + 4 students, 2 poses each (neutral, hand raised), upper body only |
| `logo.png` | optional | small pixel raised-hand icon for the logo and browser tab |

---

## 1) room.png  (attach the photo of our classroom)

I'm attaching a photo of my real MBA classroom. Redraw this classroom as an
isometric pixel-art game scene.

Keep from the photo:
- the room shape and the seating layout (rows/tiers, desk shape and direction),
- where the board/screens, the front desk or lectern, doors and windows are.

Simplify it so it reads clearly at small size:
- show only about 8–10 seats, clearly separated, all EMPTY;
- keep one clear empty spot at the front (behind the front desk or lectern) where
  the professor will stand;
- keep the board(s) or screen(s) completely EMPTY (no writing, no drawings).

Style:
- cozy but professional, soft muted pastel palette;
- warm wood desks, muted teal or blue-gray walls, cream floor or carpet;
- dark navy pixel outlines, clean crisp pixels, gentle lighting;
- NO people, NO text, NO logos, NO school names;
- very light sky blue background (#E6F4FB) around the room.

Output: wide 16:9 image, high resolution (at least 1920×1080).

## 2) characters.png  (same chat, after room.png)

Now make a pixel-art character sprite sheet in exactly the same style as that
classroom (same outline weight, same palette, chibi proportions, big heads).

- Grid: 5 rows × 2 columns, every cell the same size, character centered in
  each cell, facing 3/4 toward the viewer, at a scale that fits one seat of the
  classroom.
- Upper body only, cut off at the waist with a straight horizontal edge
  (they will appear seated behind desks).
- Rows:
  1. a middle-aged professor, gray hair, navy blazer, red tie
  2. student, black hair, coral pink hoodie (this is "me")
  3. student, brown hair, light blue shirt
  4. student, blond hair, lavender sweater
  5. student, curly dark hair, mint green shirt
- Columns: 1) neutral, hands down; 2) right hand raised high.
- Each character must look identical in both columns.
- Generic cartoon characters; they must not resemble any real person.
- Plain solid white background, no text, no grid lines, no shadows.

## 3) logo.png  (optional, same chat)

A small pixel-art icon of a raised hand with a tiny sparkle, same style and
palette, coral pink (#F47C7C) hand with dark navy outline, centered, plain solid
white background, square 512×512, no text.

---

## Check before sending to Claude
- room: seats empty, board empty, no text anywhere, the professor's spot is clear
- characters: 10 cells, same size, the same person in both poses, cut at the waist
- if a result fails a check, ask ChatGPT to fix only that point

Then send the files: white backgrounds are removed, seat coordinates are
measured, and everything is wired into the app (`static/img/`).
