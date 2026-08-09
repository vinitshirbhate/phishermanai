import sys

# Windows console defaults to cp1252, which can't encode the emoji in the Space's
# verdict string (e.g. "REAL"/"FAKE"), causing a crash on print(). Force UTF-8.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gradio_client import Client, file

# Usage: python main.py [video_path]

# HF Space: https://huggingface.co/spaces/KoreaPeter/DeepFake-Video-Detection
# Frame-by-frame video deepfake detection (MS-EffGCViT), 6 domain-specific models.
SPACE_ID = "KoreaPeter/DeepFake-Video-Detection"

# Path to the video you want to check; override with a command-line argument.
VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "samples/fake.mp4"

# "fast" (b0, 8.7M params) or "pro" (b5, 50.3M params, more accurate but slower)
VARIANT = "fast"
# "kodf" (East Asian faces), "celeb-df-v2" (celebrity faces), "ff++" (Western faces)
DATASET = "ff++"

# Advanced settings (space defaults)
NUM_FRAMES = 5
MARGIN_RATIO = 0.2
CONF_THRES = 0.5
MIN_FACE_RATIO = 0.01
TTA_HFLIP = 0.0
AGG_MODE = "conf"  # "conf" (heuristic, recommended), "mean", or "vote"


def main():
    client = Client(SPACE_ID)

    class_probabilities, result, _frame_table_html = client.predict(
        video_path=file(VIDEO_PATH),
        variant=VARIANT,
        dataset=DATASET,
        num_frames=NUM_FRAMES,
        margin_ratio=MARGIN_RATIO,
        conf_thres=CONF_THRES,
        min_face_ratio=MIN_FACE_RATIO,
        tta_hflip=TTA_HFLIP,
        agg_mode=AGG_MODE,
        api_name="/predict",
    )

    print(result)
    print()
    for entry in class_probabilities.get("confidences", []):
        print(f"{entry['label']}: {entry['confidence']:.2%}")


if __name__ == "__main__":
    main()