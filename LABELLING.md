# Labelling pass — the single biggest quality lever left

**Time: 20–40 minutes. Only you can do it.** Everything else in the naming head
is built, tested and committed; what is missing is ground truth for the rooms
you actually walk in.

## Why it matters for the review

The embedding naming head (`name_index.py`) decides *what* an object is called,
and it is the only calibrated namer in the pipeline. On the eight clips it was
taught, it corrected **104 of 105** COCO naming errors — wardrobe called
"refrigerator", dustbin called "toilet", the paper notebook called "laptop".

In the two newest rooms it makes **zero renames**. That is not a bug: the crops
it was taught come from older clips, so similarity is high (0.75–0.90) but the
*margin* between competing labels is tiny (0.005–0.11) against `MIN_MARGIN`
0.15, and it declines rather than guesses. Correct behaviour, and it means the
benefit is room-specific until the room is labelled.

Consequences you can hear today, measured on `field_walk_20260907.mp4`:

* 2 of 12 walk warnings say "Obstacle" instead of the object's name.
* A laundry basket is detected as `handbag`, which is not in `TARGET_CLASSES`,
  so the app **drops it entirely** — a waist-high floor obstacle it never warns
  about.
* Stray `refrigerator` / `toilet` / `tv` labels for a wardrobe, a dustbin and a
  window.

## What is waiting

| folder | crops | from |
|---|---|---|
| `test_output/crops_room/` | 196 in 24 folders | `room_walk_20260905.mp4` |
| `test_output/crops_field0907/` | 155 in 25 folders | `field_walk_20260907.mp4` |

Each folder is named by **YOLO's guess**. Inside each one there is now a
contact sheet, `_sheet_<name>.jpg`, showing every crop in that folder tiled and
numbered — open that first and you can usually judge a whole folder in a second
(`tools/crop_contact_sheets.py` regenerates them).

## How to do it

1. Open a folder's `_sheet_*.jpg`. Ask: **is this word right for these
   pictures?**
2. **Right** → move the crops (not the sheet) into
   `test_output/crops/<that same name>/`.
3. **Wrong** → move them into `test_output/crops/<the correct name>/`. The
   correct name must be one the app knows — see `TARGET_CLASSES` in
   `position.py`. Expected finds, based on the last pass:
   * `handbag/` → almost certainly `laundry basket`
   * `refrigerator/` → `wardrobe`
   * `toilet/` → `dustbin` (or `chair` for the cream plastic stool)
   * `tv/` → `window`
   * `laptop/` → `book` when it is the paper notebook
4. **Junk** — a hallucinated box, a wall, half an object, two objects in one
   crop → `test_output/crops/_ignore/`. This is not a discard pile: `_ignore`
   is a real label in the index, and it is what makes a junk query fail the
   margin test instead of snapping to the nearest real class. The last index
   had 72 of 280 crops in it.
5. If a class you need is missing from `TARGET_CLASSES`, tell me — adding one
   touches `position.py` + `position.dart` (class, `_AREA_THRESHOLDS`,
   `_REAL_HEIGHTS`), the voice synonyms in `voice.py` +
   `voice_commands.dart`, and `agent.py --write-manifest`.

⚠ **MOVE, do not copy.** On the last pass two crops were copied instead of
moved and ended up under two contradictory labels. Windows Explorer also
**replaces silently** when two files with the same name land in one folder —
filenames are globally unique now (`<clip>_f<frame>_<index>_<class>.jpg`), so
this should not bite again, but do not rename them.

## Then

```
venv-gpu\Scripts\python.exe build_name_index.py
```

It writes `name_index.npz` and prints a leave-one-out report plus a threshold
sweep. **Read the sweep**: take the highest-coverage row with zero wrong names.
Last time that was `MIN_SIM` 0.62 / `MIN_MARGIN` 0.15 — do not assume those
carry over to a differently-labelled index.

Then check it against the clips before trusting it:

```
venv-gpu\Scripts\python.exe verify_namer.py --stride 1
venv-gpu\Scripts\python.exe tools\replay_all_features.py test_output\field_walk_20260907.mp4
```

The second one should show renames in the "Naming head" section and fewer
"Obstacle" lines in the anomaly list.

⚠ `test_output/` is **gitignored**, so the labelled crops have no backup. The
built `name_index.npz` is tracked, so the product is safe; the raw crops are
not. Copy them to a USB stick, or say the word and I will un-ignore
`test_output/crops/` — they are photographs of your rooms, so that is your
call.
