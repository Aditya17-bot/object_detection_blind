"""BlindAssist — step 3: build the naming index from labelled crops.

Input is the folder tree the user produced by dragging files in Explorer:

    test_output/crops/dustbin/     test_output/crops/wardrobe/
    test_output/crops/chair/       test_output/crops/_ignore/
    test_output/crops/_unsorted/   <- skipped, still unlabelled

Each folder name is a label. `_ignore/` is a real label, not a discard pile:
crops that are wall texture, glare or junk boxes belong in the index so that a
query landing among them fails the margin test instead of snapping to whatever
real class happens to be nearest.

Output is `name_index.npz` (embeddings + labels) plus a leave-one-out report.
That report is the evidence the whole approach turns on: confidence could not
separate right names from wrong ones (the bands overlap — EVALUATION.md's
0.65-0.75 vs >=0.85 claim is falsified), so embedding distance has to, and this
prints the two distributions so it can be checked rather than assumed.

Run:  venv-gpu/Scripts/python.exe build_name_index.py
"""
import argparse
import pathlib
import sys

import numpy as np

from name_index import IGNORE_LABEL, MIN_MARGIN, MIN_SIM, NameIndex
from position import TARGET_CLASSES

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SKIP_FOLDERS = {"_unsorted"}
EMBED_IMGSZ = 224


def scan(crops_dir):
    """-> (paths, labels). Folder name is the label; _unsorted is skipped."""
    root = pathlib.Path(crops_dir)
    paths, labels = [], []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name in SKIP_FOLDERS:
            continue
        for img in sorted(folder.iterdir()):
            if img.suffix.lower() in IMAGE_EXTS:
                paths.append(img)
                labels.append(folder.name)
    return paths, labels


def embed_paths(model, paths, device, imgsz=EMBED_IMGSZ, batch=32):
    import cv2
    vecs, kept_idx = [], []
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        imgs, idx = [], []
        for j, p in enumerate(chunk):
            img = cv2.imread(str(p))
            if img is None:
                print(f"  !! unreadable, skipped: {p}")
                continue
            imgs.append(img)
            idx.append(i + j)
        if not imgs:
            continue
        out = model.embed(imgs, imgsz=imgsz, device=device, verbose=False)
        vecs.extend(v.detach().float().cpu().numpy() for v in out)
        kept_idx.extend(idx)
    return np.stack(vecs).astype(np.float32) if vecs else \
        np.zeros((0, 1), np.float32), kept_idx


def leave_one_out(vectors, labels, min_sim=MIN_SIM, min_margin=MIN_MARGIN):
    """Score every crop against the index with ITSELF removed.

    Without the self-exclusion every crop scores 1.0 against itself and the
    report is a meaningless 100%. Returns (rows, summary) where each row is
    (true_label, predicted_or_None, top_sim, margin, reason).
    """
    from name_index import l2_normalize
    v = l2_normalize(vectors)
    sims = v @ v.T
    np.fill_diagonal(sims, -2.0)              # exclude self
    labels = list(labels)
    rows = []
    for i, row in enumerate(sims):
        best = {}
        for lab, s in zip(labels, row):
            s = float(s)
            if s > best.get(lab, -2.0):
                best[lab] = s
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        top_label, top_sim = ranked[0]
        runner_sim = ranked[1][1] if len(ranked) > 1 else -1.0
        margin = top_sim - runner_sim
        if top_sim < min_sim:
            pred, reason = None, "below min_sim"
        elif margin < min_margin:
            pred, reason = None, "ambiguous"
        elif top_label == IGNORE_LABEL:
            # Mirror NameIndex.classify_vectors exactly. Matching _ignore is an
            # ABSTENTION at runtime — the detection keeps YOLO's word — so
            # scoring it as a wrong name overstates the error rate with the one
            # outcome that is by definition safe. The reverse (a crop the user
            # put in _ignore matching a real class) still counts as wrong,
            # because that one does put a word in the user's ear.
            pred, reason = None, "matched _ignore"
        else:
            pred, reason = top_label, "match"
        rows.append((labels[i], pred, top_sim, margin, reason))
    return rows


def sweep_thresholds(vectors, labels, sims=(0.60, 0.65, 0.70, 0.75, 0.80),
                     margins=(0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20)):
    """Find the (min_sim, min_margin) that names the most crops with NO wrong
    names, and report the whole grid.

    This is the point of the exercise. Confidence could not be thresholded —
    correct and incorrect YOLO names occupied the same 0.65-0.94 band, so no
    cut existed. If embedding distance is a real abstention signal there is a
    setting here with zero errors and useful coverage; if the zero-error column
    is empty at every setting, the signal is no better than the one it replaces
    and that has to be visible rather than assumed.
    """
    grid = []
    for ms in sims:
        for mm in margins:
            rows = leave_one_out(vectors, labels, ms, mm)
            decided = [r for r in rows if r[1] is not None]
            wrong = sum(1 for r in decided if r[1] != r[0])
            grid.append({"min_sim": ms, "min_margin": mm,
                         "named": len(decided), "wrong": wrong,
                         "correct": len(decided) - wrong})
    clean = [g for g in grid if g["wrong"] == 0]
    best = max(clean, key=lambda g: g["correct"]) if clean else None
    return grid, best


def sweep_report(grid, best, total):
    lines = ["## Threshold sweep\n",
             "Coverage vs errors over the whole grid. The row to pick is the "
             "one that names\nthe most crops with **wrong = 0**.\n",
             "| min_sim | min_margin | named | correct | wrong |",
             "|---|---|---|---|---|"]
    for g in grid:
        mark = " **<- best clean**" if g is best else ""
        lines.append(f"| {g['min_sim']:.2f} | {g['min_margin']:.2f} | "
                     f"{g['named']} | {g['correct']} | {g['wrong']}{mark} |")
    lines.append("")
    if best is None:
        lines.append("**No setting reaches zero errors.** Embedding distance "
                     "is not separating these\nclasses either — inspect the "
                     "wrong-decision crops above before shipping this; the "
                     "usual cause is two labels that are genuinely the same "
                     "object, or crops in\n`_ignore/` that belong to a real "
                     "class.\n")
    else:
        lines.append(f"Best clean setting: **min_sim {best['min_sim']:.2f}, "
                     f"min_margin {best['min_margin']:.2f}** — names "
                     f"{best['correct']}/{total} crops "
                     f"({best['correct'] / total:.0%}) with zero wrong names.\n"
                     "Set these in name_index.py (MIN_SIM / MIN_MARGIN) or "
                     "pass them to build_name_index.py.\n")
    return "\n".join(lines)


def report(rows, out_path=None, extra=""):
    """Print (and optionally write) the accuracy + separation report."""
    total = len(rows)
    decided = [r for r in rows if r[1] is not None]
    correct = [r for r in decided if r[1] == r[0]]
    wrong = [r for r in decided if r[1] != r[0]]
    abstained = [r for r in rows if r[1] is None]

    lines = []
    add = lines.append
    add("# Naming index — leave-one-out report\n")
    add(f"- crops: **{total}**")
    add(f"- decided: **{len(decided)}** "
        f"({len(decided) / total:.1%} of crops)")
    add(f"- correct when decided: **{len(correct)}/{len(decided)}** "
        f"({(len(correct) / len(decided) if decided else 0):.1%})")
    add(f"- abstained: **{len(abstained)}** "
        f"({len(abstained) / total:.1%})\n")

    # The separation that confidence could not provide. If these two rows
    # overlap the way the old confidence probe did, the gate is no better than
    # the one it replaces and the thresholds need moving before shipping.
    def band(rs, key):
        vals = [r[key] for r in rs]
        if not vals:
            return "n/a"
        vals = np.array(vals)
        return (f"min {vals.min():.3f} · p25 {np.percentile(vals, 25):.3f} · "
                f"median {np.median(vals):.3f} · max {vals.max():.3f}")

    add("## Separation (the thing confidence failed to give)\n")
    add("| decisions | similarity | margin |")
    add("|---|---|---|")
    add(f"| correct (n={len(correct)}) | {band(correct, 2)} | "
        f"{band(correct, 3)} |")
    add(f"| **wrong** (n={len(wrong)}) | {band(wrong, 2)} | "
        f"{band(wrong, 3)} |")
    add(f"| abstained (n={len(abstained)}) | {band(abstained, 2)} | "
        f"{band(abstained, 3)} |\n")

    per = {}
    for true, pred, sim, margin, reason in rows:
        d = per.setdefault(true, {"n": 0, "ok": 0, "abst": 0})
        d["n"] += 1
        if pred is None:
            d["abst"] += 1
        elif pred == true:
            d["ok"] += 1
    add("## Per class\n")
    add("| label | crops | correct | abstained | wrong |")
    add("|---|---|---|---|---|")
    for lab in sorted(per):
        d = per[lab]
        add(f"| {lab} | {d['n']} | {d['ok']} | {d['abst']} | "
            f"{d['n'] - d['ok'] - d['abst']} |")
    add("")

    if wrong:
        add("## Wrong decisions (inspect these crops)\n")
        add("| true | predicted | sim | margin |")
        add("|---|---|---|---|")
        for true, pred, sim, margin, _ in sorted(wrong, key=lambda r: -r[2]):
            add(f"| {true} | {pred} | {sim:.3f} | {margin:.3f} |")
        add("")

    text = "\n".join(lines) + extra
    print(text)
    if out_path:
        pathlib.Path(out_path).write_text(text, encoding="utf-8")
        print(f"written {out_path}")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crops", default="test_output/crops")
    ap.add_argument("--out", default="name_index.npz")
    ap.add_argument("--report", default="test_output/name_index_report.md")
    ap.add_argument("--model", default="yolov8s.pt",
                    help="MUST be the same weights the server embeds with — "
                         "vectors from different backbones are not comparable")
    ap.add_argument("--device", default=0)
    ap.add_argument("--min-sim", type=float, default=MIN_SIM)
    ap.add_argument("--min-margin", type=float, default=MIN_MARGIN)
    ap.add_argument("--allow-unknown", action="store_true",
                    help="build even if labels are outside TARGET_CLASSES "
                         "(those names fail silently downstream)")
    args = ap.parse_args(argv)

    paths, labels = scan(args.crops)
    if not paths:
        print(f"no labelled crops under {args.crops} — label some first "
              f"(everything is still in _unsorted/)")
        return 1
    counts = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    print(f"{len(paths)} crops in {len(counts)} labels:")
    for lab in sorted(counts):
        print(f"  {counts[lab]:4d}  {lab}")

    unknown = sorted(l for l in counts
                     if l != IGNORE_LABEL and l not in TARGET_CLASSES)
    if unknown:
        msg = (f"\nlabels outside position.TARGET_CLASSES: {unknown}\n"
               "  These fail SILENTLY downstream: person-sized proximity "
               "thresholds,\n  no metre estimate, and never walk-warned. Add "
               "them to OBSTACLE_CLASSES/\n  FIND_CLASSES + _AREA_THRESHOLDS "
               "+ _REAL_HEIGHTS (position.py AND position.dart),\n  or rerun "
               "with --allow-unknown.")
        if not args.allow_unknown:
            print(msg)
            return 2
        print(msg + "\n  (--allow-unknown given, building anyway)")

    from ultralytics import YOLO
    device = args.device if args.device == "cpu" else int(args.device)
    model = YOLO(args.model)
    print(f"\nembedding with {args.model} @ {EMBED_IMGSZ}px...")
    vectors, kept = embed_paths(model, paths, device)
    labels = [labels[i] for i in kept]

    index = NameIndex(vectors, labels, embed_imgsz=EMBED_IMGSZ,
                      min_sim=args.min_sim, min_margin=args.min_margin,
                      model_name=args.model)
    index.save(args.out)
    print(f"saved {args.out}: {index.vectors.shape[0]} vectors, "
          f"{index.vectors.shape[1]}-d, {len(index.classes)} labels")

    rows = leave_one_out(vectors, labels, args.min_sim, args.min_margin)
    grid, best = sweep_thresholds(vectors, labels)
    report(rows, args.report,
           extra="\n" + sweep_report(grid, best, len(labels)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
