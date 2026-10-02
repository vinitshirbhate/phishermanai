"""One-time conversion: ffpp_efficientnet_best.pth -> ffpp_efficientnet_b0.onnx

    python export_onnx.py

Run this once on a machine that has torch and timm. The result is a ~17 MB graph
that `test.py` runs with onnxruntime alone -- no torch, no timm at serve time.
That is the whole point: torch's CPU wheel does not fit in a 512 MB free-tier
box, and onnxruntime does.

WHY THE ARCHITECTURE IS SPELLED OUT HERE
----------------------------------------
The checkpoint stores weights, not code, and the training script is not in this
repo. The module tree below was recovered from the tensor shapes and verified by
loading with strict=True (zero missing, zero unexpected keys):

    backbone   timm efficientnet_b0, num_classes=0  -> 1280-d pooled features
    head.0     LayerNorm(1280)        weight+bias (1280,), no running stats
    head.1     Dropout                no parameters, no-op in eval
    head.2     Linear(1280, 256)
    head.3     activation             no parameters -- see ACTIVATION below
    head.4     Dropout                no parameters, no-op in eval
    head.5     Linear(256, 1)         single logit; sigmoid -> P(fake)

head.0 could in principle have been BatchNorm1d(track_running_stats=False),
which has the same parameter signature. It is not: BatchNorm normalises across
the batch, which would make every frame's score depend on which other frames
were in the same call, and it flattens the known-fake sample from 0.70 to 0.41.
LayerNorm is both the better-behaved reading and the better-scoring one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

try:
    import timm
except ImportError:  # pragma: no cover - export-time dependency only
    sys.exit("export needs timm:  pip install timm torch onnx")

HERE = Path(__file__).parent
CKPT = HERE / "ffpp_efficientnet_best.pth"
OUT = HERE / "ffpp_efficientnet_b0.onnx"

# head.3 has no parameters, so the checkpoint cannot tell us which activation was
# used and every candidate loads cleanly. It turns out not to matter: on the
# sample clips ReLU/GELU/SiLU land within 0.01 of each other (0.695/0.693/0.703),
# nowhere near the decision threshold. GELU is the usual partner for a LayerNorm
# head. If you still have the training notebook and it says otherwise, change
# this one line and re-export.
ACTIVATION = nn.GELU


class DeepFakeNet(nn.Module):
    """EfficientNet-B0 trunk with the checkpoint's custom binary head.

    Emits P(fake) directly -- the sigmoid is part of the exported graph so the
    serving code cannot forget to apply it, or apply it twice.
    """

    def __init__(self) -> None:
        super().__init__()
        self.backbone = timm.create_model("efficientnet_b0", pretrained=False, num_classes=0)
        self.head = nn.Sequential(
            nn.LayerNorm(1280),
            nn.Dropout(0.3),
            nn.Linear(1280, 256),
            ACTIVATION(),
            nn.Dropout(0.3),
            nn.Linear(256, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.head(self.backbone(x))).squeeze(-1)


def main() -> int:
    if not CKPT.exists():
        sys.exit(f"checkpoint not found: {CKPT}")

    # Tensors in the checkpoint are tagged cuda:0. Without map_location this
    # raises "Attempting to deserialize object on a CUDA device" on any CPU box,
    # which is every box this is going to be deployed on.
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    print(f"checkpoint  epoch={ck.get('epoch')}  val_f1={ck.get('val_f1_macro'):.4f}  "
          f"val_auc={ck.get('val_auc'):.4f}")

    model = DeepFakeNet()
    model.load_state_dict(ck["model_state_dict"], strict=True)
    model.eval()
    print(f"weights loaded  params={sum(p.numel() for p in model.parameters()):,}")

    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        dummy,
        str(OUT),
        input_names=["frames"],
        output_names=["prob_fake"],
        # Frames are batched per video and the count varies (faces are not found
        # in every sampled frame), so the batch axis has to stay dynamic.
        dynamic_axes={"frames": {0: "batch"}, "prob_fake": {0: "batch"}},
        opset_version=17,          # 17 has a native LayerNormalization op
        do_constant_folding=True,
    )
    print(f"exported    {OUT.name}  {OUT.stat().st_size / 1024 / 1024:.1f} MB "
          f"(was {CKPT.stat().st_size / 1024 / 1024:.1f} MB)")

    _verify(model)
    return 0


def _verify(model: nn.Module) -> None:
    """Numerical parity against the torch model, on real face crops.

    Verify on the input the model will actually see, not on noise. Gaussian
    noise puts an EfficientNet in an ill-conditioned regime where torch and
    onnxruntime's differing convolution kernels diverge by whole tenths of a
    probability -- and where torch is not even self-consistent (the same frame
    scored alone vs inside a batch of 16 moves by 7e-03, while the ONNX graph is
    bit-identical across batch sizes). On real face crops the two agree to about
    2e-06, which is the number that means anything.
    """
    import onnxruntime as ort

    from test import preprocess, crop_face, get_detector, iter_frames

    sess = ort.InferenceSession(str(OUT), providers=["CPUExecutionProvider"])

    clips = sorted((HERE / "samples").glob("*.mp4"))
    if not clips:
        print("parity      no samples/*.mp4 to verify against -- skipping")
        return

    detector = get_detector()
    worst = 0.0
    for clip in clips:
        tensors = []
        for frame in iter_frames(clip, 16):
            box = detector.largest_face(frame)
            if box is not None:
                tensors.append(preprocess(crop_face(frame, box)))
        if not tensors:
            print(f"parity      {clip.name}: no faces found, skipping")
            continue

        x = np.stack(tensors).astype(np.float32)
        with torch.inference_mode():
            want = model(torch.from_numpy(x)).numpy()
        got = sess.run(["prob_fake"], {"frames": x})[0]

        delta = float(np.abs(want - got).max())
        worst = max(worst, delta)
        print(f"parity      {clip.name:22} n={len(x):2d}  max|torch-onnx| = {delta:.2e}  "
              f"(torch {want.mean():.4f} / onnx {got.mean():.4f})")

    if worst > 1e-4:
        sys.exit(f"FAILED: onnx diverges from torch by {worst:.2e}")
    print(f"OK          worst {worst:.2e}")


if __name__ == "__main__":
    raise SystemExit(main())