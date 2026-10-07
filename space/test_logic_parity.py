"""space/logic.js must say exactly what the Python pipeline says.

Builds random scenes, runs them through position.py / decision.py /
detect_merge.py, then through logic.js under Node, and compares every
message. Needs `node` on PATH; skipped otherwise.

    python -m unittest space.test_logic_parity -v
"""

import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from decision import (find_message, find_target, pick_obstacle,  # noqa: E402
                      summarize_scene, walk_message)
from detect_merge import merge_detections  # noqa: E402
from position import TARGET_CLASSES, analyze_box  # noqa: E402

FLOORS = {"door": 0.4, "dustbin": 0.6}
NAMES = sorted(TARGET_CLASSES) + ["dustbin", "stairs", "person", "person", "chair", "door"]
W, H = 540, 960

NODE_RUNNER = """
import * as L from "./logic.js";
import { readFileSync } from "node:fs";
const cases = JSON.parse(readFileSync(0, "utf8"));
const out = cases.map(({ dets, target }) => {
  const merged = L.mergeDetections(dets, %s, 0.6);
  const infos = merged.map((d) => L.analyzeBox(d.name, d.conf, ...d.px, %d, %d, !!d.trusted_name));
  const ob = L.pickObstacle(infos);
  return {
    kept: merged.map((d) => d.id),
    infos: infos.map((i) => [i.phrase, i.proximity, i.distanceM]),
    walk: ob ? L.walkMessage(ob, infos, true) : null,
    walk_zones: ob ? L.walkMessage(ob, infos, false) : null,
    find: L.findMessage(L.findTarget(infos, target), target, true),
    describe: L.summarizeScene(infos),
  };
});
process.stdout.write(JSON.stringify(out));
""" % (json.dumps(FLOORS), W, H)


def _random_det(rng, i):
    name = rng.choice(NAMES)
    x1, y1 = rng.randint(0, W - 10), rng.randint(0, H - 10)
    x2, y2 = rng.randint(x1 + 5, W), rng.randint(y1 + 5, H)
    conf = round(rng.uniform(0.4, 0.99), 4)
    det = {"id": i, "name": name, "conf": conf, "px": [x1, y1, x2, y2],
           "x1": x1 / W, "y1": y1 / H, "x2": x2 / W, "y2": y2 / H}
    if name in ("door", "dustbin", "stairs"):
        det["trusted_name"] = True
    return det


def _scene(rng):
    dets = [_random_det(rng, i) for i in range(rng.randint(0, 7))]
    # near-duplicates so the cross-model merge actually fires
    for d in list(dets)[:2]:
        if rng.random() < 0.5:
            twin = dict(d, id=len(dets), name=rng.choice(["dustbin", "suitcase", d["name"]]),
                        conf=round(rng.uniform(0.4, 0.99), 4))
            dets.append(twin)
    return dets


def _python(dets, target):
    merged = merge_detections(dets, floors=dict(FLOORS), default_floor=0.6)
    infos = [analyze_box(d["name"], d["conf"], *d["px"], W, H,
                         trusted_name=bool(d.get("trusted_name"))) for d in merged]
    ob = pick_obstacle(infos)
    return {
        "kept": [d["id"] for d in merged],
        "infos": [[i.phrase, i.proximity, i.distance_m] for i in infos],
        "walk": walk_message(ob, infos, use_clock=True) if ob else None,
        "walk_zones": walk_message(ob, infos, use_clock=False) if ob else None,
        "find": find_message(find_target(infos, target), target, use_clock=True),
        "describe": summarize_scene(infos),
    }


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class TestLogicParity(unittest.TestCase):
    def test_logic_js_matches_python(self):
        rng = random.Random(0)
        cases = [{"dets": _scene(rng), "target": rng.choice(sorted(TARGET_CLASSES))}
                 for _ in range(2000)]
        here = Path(__file__).resolve().parent
        # the runner must sit next to logic.js for its relative import
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", dir=here, delete=False,
                                         encoding="utf-8") as f:
            f.write(NODE_RUNNER)
        runner = Path(f.name)
        try:
            proc = subprocess.run(["node", str(runner)], input=json.dumps(cases),
                                  capture_output=True, text=True, encoding="utf-8",
                                  check=True)
        finally:
            runner.unlink()
        for case, got in zip(cases, json.loads(proc.stdout)):
            self.assertEqual(got, _python(case["dets"], case["target"]), case)


if __name__ == "__main__":
    unittest.main()
