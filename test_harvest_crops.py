"""Tests for harvest_crops.py — the crop-harvesting step.

Only the parts that do not need a model or a video file: filename construction
and the manifest. Those are exactly where the 2026-08-02 labelling pass lost
data, so they are worth pinning.
"""
import csv
import pathlib
import tempfile
import unittest

import numpy as np

import harvest_crops as H


def record(clip, frame, name, conf, source="coco"):
    return {"clip": clip, "frame": frame, "name": name, "conf": conf,
            "source": source, "crop": np.zeros((8, 8, 3), np.uint8),
            "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}


class WriteCropsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "crops"

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_detections_in_one_frame_never_share_a_filename(self):
        """The bug that cost three crops.

        Labelling flattens every guess-folder into one label folder, and
        Explorer replaces silently on a same-name move. The old filename ended
        in int(conf * 100), so two boxes in the same frame of the same clip
        that rounded to the same confidence produced the same name — different
        folders at harvest time, one surviving file after labelling. One of the
        three lost that way was a dustbin, a class with five examples.
        """
        records = [record("clipA", 110, "toilet", 0.5049),
                   record("clipA", 110, "dustbin", 0.5051),
                   record("clipA", 110, "sink", 0.5000)]
        H.write_crops(records, range(len(records)), self.out)
        names = [p.name for p in self.out.rglob("*.jpg")]
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3, f"filenames collided: {names}")

    def test_filename_carries_the_class_so_it_survives_being_moved(self):
        records = [record("clipA", 7, "potted plant", 0.9)]
        H.write_crops(records, [0], self.out)
        name = next(self.out.rglob("*.jpg")).name
        self.assertIn("potted_plant", name)
        self.assertIn("clipA", name)
        self.assertIn("f00007", name)

    def test_crops_land_in_a_folder_per_yolo_guess(self):
        records = [record("c", 1, "toilet", 0.9), record("c", 2, "toilet", 0.8),
                   record("c", 3, "dining table", 0.7)]
        H.write_crops(records, range(3), self.out)
        folders = sorted(p.name for p in self.out.iterdir() if p.is_dir())
        self.assertEqual(folders, ["dining_table", "toilet"])

    def test_manifest_row_per_crop_with_the_box_it_came_from(self):
        records = [record("clipA", 110, "toilet", 0.5049),
                   record("clipA", 110, "dustbin", 0.5051)]
        manifest = H.write_crops(records, [0, 1], self.out)
        with open(manifest, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["yolo_name"] for r in rows}, {"toilet", "dustbin"})
        # the box is what lets a lost crop be regenerated from the clip
        self.assertEqual(rows[0]["x1"], "0.1")
        self.assertEqual(rows[0]["frame"], "110")
        # every manifest path must point at a file that exists
        for r in rows:
            self.assertTrue((self.out.parent / r["file"]).exists(), r["file"])

    def test_skipped_records_are_not_written(self):
        records = [record("c", 1, "toilet", 0.9), record("c", 2, "toilet", 0.8)]
        H.write_crops(records, [1], self.out)
        self.assertEqual(len(list(self.out.rglob("*.jpg"))), 1)


class SafeNameTest(unittest.TestCase):
    def test_spaces_become_underscores(self):
        self.assertEqual(H.safe_name("dining table"), "dining_table")

    def test_path_separators_cannot_escape_the_folder(self):
        self.assertNotIn("/", H.safe_name("a/b"))
        self.assertNotIn("\\", H.safe_name("a\\b"))


if __name__ == "__main__":
    unittest.main()
