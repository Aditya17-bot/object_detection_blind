#!/bin/bash
# One-time WSL setup for TFLite export (ultralytics litert export is Linux-only)
set -e
python3 -m venv ~/yolo_env
source ~/yolo_env/bin/activate
pip install -q --upgrade pip
pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -q ultralytics tensorflow-cpu
python - <<'EOF'
import ultralytics, tensorflow
print("WSL deps OK", ultralytics.__version__, tensorflow.__version__)
EOF
