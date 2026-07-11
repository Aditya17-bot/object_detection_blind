# Adding door + dustbin (+ stairs) detection — handoff notes

Goal: BlindAssist should detect **doors**, **dustbins** and **stairs**. None
is a COCO class, so our `yolov8s.pt` cannot see them (our tests confirm it:
the blue dustbin gets misdetected as "toilet").

> STATUS 2026-07-11: the user is training this themselves on Colab with all
> three classes. Deliverables when done: `best.pt`, the `data.yaml` (class
> name order!), imgsz used, and a few val prediction images.

## The one thing to understand first

**You cannot open `yolov8s.pt` and "add" classes to it.** A `.pt` file is just
trained weights for exactly the 80 COCO classes. Adding a class means
*training* on labeled images of that class (called fine-tuning / transfer
learning). The good news: Ultralytics makes this a few commands, and a free
Google Colab GPU is enough.

## Two ways to do it

### Option A — separate small model (recommended, simplest)
Train a brand-new small model (`yolov8n.pt` as the base) on ONLY door +
dustbin images. The app then runs two models per frame: the normal COCO one
plus this one.

- Pro: easy dataset (just doors + dustbins), no risk of breaking the 80 COCO
  classes, cleanly testable on its own.
- Con: second inference pass, roughly +80 ms/frame on our machine (~7 FPS →
  ~4-5 FPS). Acceptable for the prototype.

### Option B — one merged model
Fine-tune `yolov8s.pt` on a dataset that contains door + dustbin **and**
examples of the COCO classes we use (person, chair, bed, ...).

- WARNING: if you fine-tune on doors/dustbins alone, the model **forgets**
  the original 80 classes ("catastrophic forgetting") and the whole app
  breaks. You must merge in COCO images, which is real dataset-wrangling work.
- Only pick this if you want the extra challenge; Option A first.

## Steps (Option A)

1. **Dataset**: Roboflow Universe (free account) has ready-made "door
   detection" and "garbage bin / trash can" datasets with images + labels.
   Download in "YOLOv8" format. Merge them into one dataset with 2 classes:
   `door`, `dustbin`. Aim for 500+ images per class.
2. **Own photos**: add ~100-200 photos of the actual doors/dustbins around
   the test rooms (different angles, lighting, half-open doors). Label them
   in Roboflow. This matters more than raw dataset size.
3. **Train on Colab** (free GPU, ~30-60 min):
   ```
   pip install ultralytics
   yolo detect train data=data.yaml model=yolov8n.pt epochs=60 imgsz=640
   ```
   `data.yaml` comes with the Roboflow download.
4. **Check results**: look at `runs/detect/train/` — confusion matrix and
   val predictions. mAP50 above ~0.7 is fine for our use.
5. **Deliverable**: the file `runs/detect/train/weights/best.pt`, renamed to
   `door_dustbin.pt`, plus 3-4 val prediction images for the report.

## Integration (our side, don't worry about it)

`position.py` works on class names, so we just load the second model,
add `door` and `dustbin` to OBSTACLE_CLASSES with area thresholds, and merge
detections from both models before position analysis.

## Timing

Agreed plan: this happens AFTER phases 3-5 (decision logic, TTS, testing) are
done. Nothing needs to be downloaded or trained yet.
