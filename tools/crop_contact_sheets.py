"""Render one contact sheet per harvested guess-folder, so the labelling pass
can be done by eye instead of by opening 350 files.

harvest_crops.py sorts crops into folders named by YOLO's guess. The labelling
job is to spot the folders where the guess is WRONG — the 2026-09-05 harvest
put the laundry basket in `handbag/`, which is the kind of thing a single tiled
image shows in one second and a file browser hides.

    venv\\Scripts\\python.exe tools/crop_contact_sheets.py test_output/crops_room

Writes <folder>/_sheet_<name>.jpg for each guess folder, plus an index of what
was found. Sheets are named with a leading underscore so they sort first and
are easy to delete before building the index.
"""
import argparse
import math
import os

import cv2
import numpy as np

TILE = 160
COLS = 8
PAD = 6
LABEL_H = 18


def sheet_for(folder, out_path, cols=COLS, tile=TILE):
    files = sorted(f for f in os.listdir(folder)
                   if f.lower().endswith((".jpg", ".jpeg", ".png"))
                   and not f.startswith("_"))
    if not files:
        return 0
    cols = max(1, min(cols, len(files)))   # a 1-crop folder gets a 1-wide sheet
    rows = math.ceil(len(files) / cols)
    cell = tile + PAD
    canvas = np.full((rows * (cell + LABEL_H) + PAD, cols * cell + PAD, 3),
                     32, np.uint8)
    for i, name in enumerate(files):
        img = cv2.imread(os.path.join(folder, name))
        if img is None:
            continue
        h, w = img.shape[:2]
        scale = tile / max(h, w)
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        r, c = divmod(i, cols)
        y = PAD + r * (cell + LABEL_H)
        x = PAD + c * cell
        canvas[y:y + img.shape[0], x:x + img.shape[1]] = img
        cv2.putText(canvas, str(i + 1), (x + 2, y + tile + LABEL_H - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1,
                    cv2.LINE_AA)
    cv2.imwrite(out_path, canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="folder of guess-named crop folders")
    ap.add_argument("--cols", type=int, default=COLS)
    ap.add_argument("--tile", type=int, default=TILE)
    args = ap.parse_args()

    names = sorted(d for d in os.listdir(args.root)
                   if os.path.isdir(os.path.join(args.root, d)))
    total = 0
    print(f"{'guess folder':22} {'crops':>5}  sheet")
    for name in names:
        folder = os.path.join(args.root, name)
        out = os.path.join(folder, f"_sheet_{name}.jpg")
        n = sheet_for(folder, out, args.cols, args.tile)
        total += n
        print(f"{name:22} {n:5}  {out}")
    print(f"\n{total} crops in {len(names)} folders")


if __name__ == "__main__":
    main()
