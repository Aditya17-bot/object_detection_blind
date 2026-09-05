"""BlindAssist — step 1 of the embedding-based naming head: harvest crops.

Why this exists
---------------
YOLO localises well and names badly: COCO has no word for wardrobe, dustbin or
window, so the detector makes a forced choice over 80 words and picks the
nearest one (the user's dustbin is confidently "toilet" at 0.94). The fix is to
keep YOLO for *where* and re-decide *what* from an embedding of the crop matched
against user-labelled examples. This script produces the examples to label.

It walks the recorded clips in test_output/, samples frames, detects with a LOW
confidence floor and NO class filter (objects YOLO calls "vase" or "oven" must
still be captured), and writes each box as a JPEG.

Two things keep the labelling job small:
  * crops are pre-sorted into a folder per YOLO guess, so a whole folder of
    "toilet" crops is almost certainly one dustbin and gets confirmed at once;
  * near-duplicate views are dropped by embedding similarity — consecutive
    frames of one object are nearly identical.

CRITICAL: crops come from a clean copy of the frame. Every JPEG already in
test_output/ has boxes, the 3x3 grid and text burned into the pixels
(phase2_detect.py draws in place), which would poison the index.

Run:  venv-gpu/Scripts/python.exe harvest_crops.py
Then label by dragging folders/files in Explorer (see build_name_index.py).
"""
import argparse
import csv
import json
import os
import pathlib
import sys

import cv2
import numpy as np

# Frames-per-clip sampling and geometry floors. A box smaller than this is not
# something the app would ever announce, and its crop is too coarse to embed.
MIN_BOX_AREA_FRAC = 0.004      # 0.4% of the frame
MIN_BOX_PX = 24                # shortest side, in pixels of the source frame

# Cosine similarity above which two crops of the same YOLO class in the same
# clip count as the same view. 0.95 keeps distinct angles, drops duplicates.
DEDUPE_SIM = 0.95

# Hard cap on crops kept per YOLO class name (the folder the user labels).
# Dedupe alone left 105 "chair" crops of essentially two chairs; a nearest-
# neighbour index gains nothing from the 90th view and the labelling job grows
# for free. The survivors are chosen by farthest-point sampling, so the cap
# keeps the MOST DIFFERENT views rather than the first N.
MAX_PER_NAME = 15

EMBED_IMGSZ = 224              # crops are small; full 640 buys nothing here


def list_clips(folder):
    """Every video in the folder, sorted for reproducible output names."""
    exts = {".mp4", ".mov", ".avi", ".mkv"}
    return sorted(p for p in pathlib.Path(folder).iterdir()
                  if p.suffix.lower() in exts)


def clip_tag(path):
    """Short filesystem-safe tag for a clip, used in crop filenames."""
    stem = path.stem
    # The WhatsApp clips share a long prefix; keep the distinguishing tail.
    keep = "".join(c if c.isalnum() else "_" for c in stem)
    return keep[-28:].strip("_")


def crop_box(frame, det, pad=0.06):
    """Pixel crop for one normalized xyxy detection, with a small context pad.

    A little context helps the embedding: a bare dustbin rectangle and a bare
    toilet rectangle are both "white-ish blob", the surrounding floor/wall is
    part of what distinguishes them.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1 = int(max(0.0, x1 - px) * w)
    x2 = int(min(1.0, x2 + px) * w)
    y1 = int(max(0.0, y1 - py) * h)
    y2 = int(min(1.0, y2 + py) * h)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return frame[y1:y2, x1:x2].copy()


def detect_frame(models, frame, conf):
    """Run every model over one frame -> list of normalized detection dicts.

    No TARGET_CLASSES filter on purpose: the whole point is to see the boxes
    the pipeline currently mislabels, including ones it discards today.
    """
    out = []
    for tag, model in models:
        res = model.predict(frame, conf=conf, imgsz=640, verbose=False)[0]
        for b in res.boxes:
            x1, y1, x2, y2 = (float(t) for t in b.xyxyn[0])
            if (x2 - x1) * (y2 - y1) < MIN_BOX_AREA_FRAC:
                continue
            h, w = frame.shape[:2]
            if min((x2 - x1) * w, (y2 - y1) * h) < MIN_BOX_PX:
                continue
            out.append({"name": model.names[int(b.cls)], "conf": float(b.conf),
                        "source": tag,
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return out


def harvest_clip(path, models, embedder, stride, conf, device):
    """Sample one clip -> list of records {crop, name, conf, clip, frame_idx}."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  !! cannot open {path.name}")
        return []
    tag = clip_tag(path)
    records, idx = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            clean = frame.copy()           # BEFORE anything can draw on it
            for det in detect_frame(models, clean, conf):
                crop = crop_box(clean, det)
                if crop is not None:
                    records.append({"crop": crop, "clip": tag, "frame": idx,
                                    **{k: v for k, v in det.items()}})
        idx += 1
    cap.release()
    print(f"  {path.name}: {idx} frames, {len(records)} raw crops")
    return records


def embed_all(embedder, crops, device, batch=32):
    """L2-normalized embedding matrix (n, d) for a list of BGR crops."""
    vecs = []
    for i in range(0, len(crops), batch):
        chunk = crops[i:i + batch]
        out = embedder.embed(chunk, imgsz=EMBED_IMGSZ, device=device,
                             verbose=False)
        vecs.extend(v.detach().float().cpu().numpy() for v in out)
    if not vecs:
        return np.zeros((0, 1), np.float32)
    m = np.stack(vecs).astype(np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(n, 1e-8)


def dedupe(records, vecs, sim=DEDUPE_SIM):
    """Greedy near-duplicate removal within each (clip, YOLO name) group.

    Consecutive frames of a stationary object give near-identical vectors; one
    representative per cluster is enough and keeps the labelling job human-sized.
    """
    keep = []
    groups = {}
    for i, r in enumerate(records):
        groups.setdefault((r["clip"], r["name"]), []).append(i)
    for _, idxs in groups.items():
        reps = []
        for i in idxs:
            v = vecs[i]
            if any(float(v @ vecs[j]) >= sim for j in reps):
                continue
            reps.append(i)
        keep.extend(reps)
    return sorted(keep)


def cap_per_name(records, vecs, keep, cap=MAX_PER_NAME):
    """Trim each YOLO-name group to `cap` crops by farthest-point sampling.

    Greedy: start from the highest-confidence crop, then repeatedly add the
    crop whose similarity to everything already chosen is lowest. That yields
    the most varied `cap` views (different angles, lighting, distances) instead
    of `cap` near-copies from one moment of one clip.
    """
    by_name = {}
    for i in keep:
        by_name.setdefault(records[i]["name"], []).append(i)
    out = []
    for _, idxs in by_name.items():
        if len(idxs) <= cap:
            out.extend(idxs)
            continue
        seed = max(idxs, key=lambda i: records[i]["conf"])
        chosen = [seed]
        # max similarity of each candidate to the chosen set, updated per pick
        best_sim = {i: float(vecs[i] @ vecs[seed]) for i in idxs if i != seed}
        while len(chosen) < cap and best_sim:
            pick = min(best_sim, key=best_sim.get)
            del best_sim[pick]
            chosen.append(pick)
            for i in list(best_sim):
                best_sim[i] = max(best_sim[i], float(vecs[i] @ vecs[pick]))
        out.extend(chosen)
    return sorted(out)


def safe_name(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def write_crops(records, keep, out_dir):
    """Write kept crops into out_dir/<yolo guess>/ plus a manifest CSV."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in keep:
        r = records[i]
        folder = out / safe_name(r["name"])
        folder.mkdir(exist_ok=True)
        # The filename must be unique across the WHOLE output, not just within
        # this folder: labelling flattens every folder into one label folder,
        # and Windows Explorer silently replaces on a same-name move. The old
        # suffix was conf*100, which collides whenever two detections in one
        # frame round to the same confidence — that cost 3 crops in the
        # 2026-08-02 labelling pass, one of them a dustbin. The record index is
        # unique by construction; the class is carried along so the guess is
        # still readable after the crop has been moved out of its folder.
        fname = (f"{r['clip']}_f{r['frame']:05d}_{i:03d}"
                 f"_{safe_name(r['name'])}.jpg")
        path = folder / fname
        cv2.imwrite(str(path), r["crop"])
        rows.append({"file": str(path.relative_to(out.parent)),
                     "yolo_name": r["name"], "conf": round(r["conf"], 3),
                     "source": r["source"], "clip": r["clip"],
                     "frame": r["frame"],
                     "x1": round(r["x1"], 4), "y1": round(r["y1"], 4),
                     "x2": round(r["x2"], 4), "y2": round(r["y2"], 4)})
    manifest = out.parent / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                            ["file", "yolo_name", "conf", "source", "clip",
                             "frame", "x1", "y1", "x2", "y2"])
        wr.writeheader()
        wr.writerows(rows)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clips", default="test_output",
                    help="folder of recorded clips to sample")
    ap.add_argument("--out", default="test_output/crops/_unsorted")
    ap.add_argument("--model", default="yolov8s.pt")
    ap.add_argument("--extra-model", default="door_dustbin_stairs.pt",
                    help="custom model; skipped if the file is missing")
    ap.add_argument("--stride", type=int, default=10,
                    help="sample every Nth frame")
    ap.add_argument("--conf", type=float, default=0.25,
                    help="deliberately BELOW the app's 0.6 — mislabelled and "
                         "weakly-detected objects are exactly what we want")
    ap.add_argument("--max-per-name", type=int, default=MAX_PER_NAME,
                    help="cap crops kept per YOLO class (farthest-point "
                         "sampled, so the survivors are the varied ones)")
    ap.add_argument("--device", default=0,
                    help="0 for the GPU, 'cpu' to force CPU")
    args = ap.parse_args(argv)

    from ultralytics import YOLO  # imported late: keeps --help instant

    device = args.device if args.device == "cpu" else int(args.device)
    coco = YOLO(args.model)
    models = [("coco", coco)]
    if os.path.exists(args.extra_model):
        models.append(("custom", YOLO(args.extra_model)))
        print(f"custom model: {sorted(models[-1][1].names.values())}")
    else:
        print(f"no custom model at {args.extra_model} — COCO only")

    clips = list_clips(args.clips)
    if not clips:
        print(f"no clips in {args.clips}")
        return 1
    print(f"{len(clips)} clips, every {args.stride}th frame, conf {args.conf}")

    records = []
    for clip in clips:
        records += harvest_clip(clip, models, coco, args.stride, args.conf,
                                device)
    if not records:
        print("no crops harvested")
        return 1

    print(f"embedding {len(records)} crops...")
    vecs = embed_all(coco, [r["crop"] for r in records], device)
    keep = dedupe(records, vecs)
    print(f"deduped {len(records)} -> {len(keep)} distinct views")
    keep = cap_per_name(records, vecs, keep, args.max_per_name)
    print(f"capped at {args.max_per_name}/class -> {len(keep)} crops to label")

    manifest = write_crops(records, keep, args.out)
    counts = {}
    for i in keep:
        counts[records[i]["name"]] = counts.get(records[i]["name"], 0) + 1
    print(f"\nwritten to {args.out}/ (manifest: {manifest})")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {name}")
    print(json.dumps({"raw": len(records), "kept": len(keep)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
