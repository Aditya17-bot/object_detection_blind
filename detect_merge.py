"""Merging two detectors' output into one answer per object.

`infer_server` runs yolov8s and the custom door/dustbin model over the same
frame and used to simply CONCATENATE their detections. Each model NMSes its own
output, so neither ever saw the other's boxes, and one physical object could
come back twice under two different names. The user's report, 2026-09-05:

    "my suitcase is shown as both dustbin and suitcase"

and the device log for a single frame:

    suitcase@0.91  backpack@0.70  dustbin@0.81  dustbin@0.70  dustbin@0.46

Downstream this is not merely untidy: `describe` lists the object twice, `count`
is wrong, the object memory stores both names, and walk mode can warn about the
same thing under two words.

Two decisions here are deliberate and worth keeping.

**Overlap is measured by IoU, never by containment.** Containment (intersection
over the smaller box) looks like the natural test for "a dustbin box inside the
suitcase box", and it is actively dangerous: measured on the user's own room
clip, the pairs it flags include *person inside bed* — a person standing in
front of a bed is contained by it. Suppressing a person is a safety regression,
and nesting is exactly how a bottle on a table or a person in a doorway looks.
High mutual IoU means the two boxes describe the same REGION; containment only
means one is inside the other.

**Confidence is compared as margin above each model's OWN floor.** The two
models are thresholded differently (COCO 0.6, custom 0.4), so raw confidences
are not comparable: 0.55 is a weak custom detection but would be below COCO's
bar entirely. `(conf - floor) / (1 - floor)` puts both on a "how far above its
own bar" scale.
"""

# Boxes this similar describe the same region, so only one name can be right.
# Different classes need stronger evidence than a same-class duplicate, which
# is certainly one object seen twice.
IOU_SAME_CLASS = 0.45
IOU_CROSS_CLASS = 0.55

# Never suppressed. A person is the detection whose loss costs most, and the
# measured false-suppression case (person contained in a bed's box) is exactly
# this class.
PROTECTED = frozenset({"person"})


def iou(a, b):
    """Intersection over union of two normalized boxes."""
    ix1, iy1 = max(a["x1"], b["x1"]), max(a["y1"], b["y1"])
    ix2, iy2 = min(a["x2"], b["x2"]), min(a["y2"], b["y2"])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = (_area(a) + _area(b) - inter)
    return inter / union if union > 0 else 0.0


def _area(d):
    return max(0.0, d["x2"] - d["x1"]) * max(0.0, d["y2"] - d["y1"])


def _score(det, floors, default_floor):
    """How far above its own model's threshold this detection sits, 0..1.

    A rename committed by the naming head outranks both models: it is the only
    part of the pipeline whose naming decision is calibrated (see name_index).
    """
    floor = floors.get(det["name"], default_floor)
    margin = (det["conf"] - floor) / max(1e-6, 1.0 - floor)
    margin = min(max(margin, 0.0), 1.0)
    return (1 if "yolo_name" in det else 0, margin)


def merge_detections(dets, floors=None, default_floor=0.5,
                     iou_same=IOU_SAME_CLASS, iou_cross=IOU_CROSS_CLASS,
                     protected=PROTECTED):
    """Return `dets` with same-object duplicates removed, best name kept.

    Order is preserved for whatever survives. Pure: no model, no frame, so it
    is testable with plain dicts.
    """
    if len(dets) < 2:
        return list(dets)

    order = sorted(range(len(dets)),
                   key=lambda i: _score(dets[i], floors or {}, default_floor),
                   reverse=True)
    dropped = set()
    for rank, i in enumerate(order):
        if i in dropped:
            continue
        for j in order[rank + 1:]:
            if j in dropped:
                continue
            if dets[j]["name"] in protected:
                continue
            same = dets[i]["name"] == dets[j]["name"]
            if iou(dets[i], dets[j]) >= (iou_same if same else iou_cross):
                dropped.add(j)
    return [d for k, d in enumerate(dets) if k not in dropped]


def merge_report(dets, kept):
    """One-line summary of what was suppressed, for the server log. Empty when
    nothing was: a silent dedup would be impossible to audit from the field."""
    if len(kept) == len(dets):
        return ""
    kept_ids = {id(d) for d in kept}
    gone = [d["name"] for d in dets if id(d) not in kept_ids]
    return "merged %d dup(s): %s" % (len(gone), ", ".join(sorted(gone)))
