"""Settings for the video deepfake detector.

Deliberately imports no torch. The serving path is onnxruntime + OpenCV only,
which is what lets this run in a 512 MB free-tier container -- torch's CPU wheel
alone does not fit. torch is needed once, by export_onnx.py, on a dev machine.
"""

import os
from pathlib import Path

HERE = Path(__file__).parent

# The exported graph. Produced by `python export_onnx.py` from the original
# ffpp_efficientnet_best.pth (49.7 MB, two thirds of which was AdamW optimizer
# state that inference never touches).
MODEL_PATH = Path(os.environ.get("DEEPFAKE_MODEL_PATH", HERE / "ffpp_efficientnet_b0.onnx"))

# The original training checkpoint. Only export_onnx.py reads this; it does not
# need to ship to production.
CHECKPOINT_PATH = HERE / "ffpp_efficientnet_best.pth"

# onnxruntime execution providers, best first. CPU is the realistic deployment
# target; CUDA is used automatically if onnxruntime-gpu happens to be installed.
PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]

# On a shared/throttled vCPU (Render free gives 0.1) extra threads cost more in
# contention than they win in parallelism. 0 means "let onnxruntime decide".
INTRA_OP_THREADS = int(os.environ.get("ONNX_INTRA_OP_THREADS", 1))

# Above this the clip is called FAKE. The head emits a single logit and the
# sigmoid is baked into the ONNX graph, so the model's output is already P(fake).
PREDICTION_THRESHOLD = float(os.environ.get("PREDICTION_THRESHOLD", 0.5))

# Video processing -- these two mirror the values in the checkpoint's own
# `config` dict, so they match how the model was trained. Do not change them
# without retraining.
FRAMES_PER_CLIP = 16
IMG_SIZE = 224

# Frames are scored in chunks rather than one big batch.
#
# Measured: this knob does not matter for memory. Batch 8 and batch 1 both peak
# within 2 MB of each other -- inference on B0 is simply cheap. What costs
# memory is video decoding (see the note on MAX_DECODE_PIXELS), so leave this
# where it is and spend the attention there.
BATCH_SIZE = int(os.environ.get("DEEPFAKE_BATCH_SIZE", 8))

# MEMORY, MEASURED (peak working set, one process, Windows/CPython 3.13)
# ---------------------------------------------------------------------
#   imports only (numpy + cv2 + onnxruntime)     53 MB
#   graph loaded, idle                          100 MB
#   scoring a still image                       203 MB
#   scoring a 288x512 clip                      306 MB
#   scoring a 1920x1920 clip                    458 MB
#   three clips back to back                    331 MB   (no leak)
#
# The model is not what costs -- inference is a rounding error, and batch 8 vs
# batch 1 differ by under 2 MB. Two other things cost. Opening any video at all
# pulls in FFmpeg and its buffers, worth ~100 MB flat; on top of that the decode
# buffers scale with resolution, because H.264 holds up to 16 reference frames
# and at 1920x1920 each one is 11 MB.
#
# So: this fits a 512 MB container handling one request at a time, with perhaps
# 50 MB to spare on a 1080p input. It does not fit two concurrent requests.
# Serve it single-worker, and guard the boundary rather than hoping -- reject or
# pre-downscale anything above this many pixels per frame (1920x1080 is 2.07 M).
MAX_DECODE_PIXELS = int(os.environ.get("DEEPFAKE_MAX_PIXELS", 2_100_000))

# ImageNet normalization (same as training)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# FACE CROPPING -- not optional, despite what the original config implied.
# This model was trained on FaceForensics++, which is a face-crop dataset. Fed
# whole frames it is out of distribution and reads everything as real: the known
# deepfake in samples/fake.mp4 scores 0.147 on whole frames and 0.693 on face
# crops. The crop is what makes the model work at all.
USE_FACE_CROP = os.environ.get("DEEPFAKE_FACE_CROP", "1") == "1"

# Padding around the detector's box, as a fraction of its width/height. Tight is
# better: 0.0 -> 0.693, 0.2 -> 0.686, 0.4 -> 0.594 on the same known fake. The
# manipulation artefacts are in the face, and margin dilutes them with
# background the model was never asked to judge.
FACE_MARGIN = float(os.environ.get("DEEPFAKE_FACE_MARGIN", 0.0))

# Ignore detections smaller than this fraction of the frame's shorter side --
# they are usually background faces or false positives, and upscaling a 30 px
# box to 224 px feeds the model interpolation artefacts rather than evidence.
MIN_FACE_RATIO = float(os.environ.get("DEEPFAKE_MIN_FACE_RATIO", 0.05))

# Optional upgrade path. OpenCV bundles the Haar cascade, so the default needs
# no extra file and works offline. YuNet is markedly better at non-frontal faces
# (Haar missed 7 of 16 frames on samples/fake.mp4); drop
# face_detection_yunet_2023mar.onnx (~340 KB) in this directory to use it.
YUNET_PATH = HERE / "face_detection_yunet_2023mar.onnx"

# How per-frame scores become one verdict: "topk" | "mean" | "max".
#
# "mean" is the wrong default. Only some frames of a deepfake carry visible
# manipulation, and averaging over the clean ones buries the signal -- on
# samples/deepfake_video.mp4 the mean is 0.394 (reads REAL, wrong) while the top
# quarter of frames average 0.700 (reads FAKE, right). "max" overcorrects and
# will convict a clip on one bad frame. "topk" is the compromise.
AGGREGATION = os.environ.get("DEEPFAKE_AGGREGATION", "topk")
TOPK_FRACTION = float(os.environ.get("DEEPFAKE_TOPK_FRACTION", 0.25))
TOPK_MIN = 3

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")