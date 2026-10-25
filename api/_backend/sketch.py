"""Sketch recognition — is this character art a manga sketch?

Two paths, faithful to the user-provided sketch-recog project:
  1. CNN (torch): ImprovedCNN fine-tuned on manga/non-manga (weights shipped
     in the repo) — used when torch + weights are available (local dev).
  2. Heuristics (numpy-only): edge density, gradients, flat-color analysis,
     spiky-feature ratio — always available, including serverless.

The combined verdict follows the original app's agreement logic: when the two
paths agree, trust them; when they disagree, the heuristic can promote.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import numpy as np

def _data_root() -> Path:
    env = os.environ.get("SAKURASCORE_BACKEND_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "backend 111" / "redbull-thapar-japan"

MODEL_PATH = _data_root() / "data" / "sketch_model" / "manga_custom_finetuned.pth"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_torch_model = None


def _load_model():
    """Lazy-load the CNN. Returns None when torch/weights are unavailable."""
    global _torch_model
    if _torch_model is not None:
        return _torch_model
    try:
        import torch  # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415
        import torch.nn.functional as F  # noqa: PLC0415

        class ImprovedCNN(nn.Module):
            """The original ImprovedCNN architecture (verbatim port)."""

            def __init__(self):
                super().__init__()
                self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
                self.bn1 = nn.BatchNorm2d(32)
                self.pool1 = nn.MaxPool2d(2, 2)
                self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
                self.bn2 = nn.BatchNorm2d(64)
                self.pool2 = nn.MaxPool2d(2, 2)
                self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
                self.bn3 = nn.BatchNorm2d(128)
                self.pool3 = nn.MaxPool2d(2, 2)
                self.global_pool = nn.AdaptiveAvgPool2d((1, 1))
                self.fc1 = nn.Linear(128, 256)
                self.dropout = nn.Dropout(0.5)
                self.fc2 = nn.Linear(256, 1)
                self.sigmoid = nn.Sigmoid()

            def forward(self, x):
                x = F.relu(self.bn1(self.conv1(x)))
                x = self.pool1(x)
                x = F.relu(self.bn2(self.conv2(x)))
                x = self.pool2(x)
                x = F.relu(self.bn3(self.conv3(x)))
                x = self.pool3(x)
                x = self.global_pool(x)
                x = x.view(x.size(0), -1)
                x = F.relu(self.fc1(x))
                x = self.dropout(x)
                x = self.sigmoid(self.fc2(x))
                return x

        m = ImprovedCNN()
        if MODEL_PATH.exists():
            m.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
            m.eval()
            _torch_model = m
    except Exception:
        _torch_model = None
    return _torch_model


def _heuristics(img_array: np.ndarray) -> tuple[float, dict]:
    """Port of enhanced_manga_heuristics — numpy-only, deterministic
    (unique-color variance instead of sklearn KMeans, per the original's
    ImportError fallback path)."""
    gray = np.mean(img_array.astype(np.float32), axis=2)

    laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    padded = np.pad(gray, 1, mode="edge")
    convolved = (
        padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] - 4 * gray
    )
    edge_density = float(np.var(convolved))

    gx = (np.roll(gray, 1, axis=0) - np.roll(gray, -1, axis=0)) * 0.5
    gy = (np.roll(gray, 1, axis=1) - np.roll(gray, -1, axis=1)) * 0.5
    gradient_magnitude = np.sqrt(gx ** 2 + gy ** 2)
    gradient_magnitude = np.where(gradient_magnitude == 0, 1e-8, gradient_magnitude)
    avg_gradient = float(np.mean(gradient_magnitude))
    p80 = np.percentile(gradient_magnitude, 80)
    high_contrast_ratio = float(np.sum(gradient_magnitude > p80) / gradient_magnitude.size)

    pixels = img_array.reshape(-1, 3)
    quant = (np.floor(pixels / 50.0)).astype(np.int64)
    _, unique_counts = np.unique(quant, axis=0, return_counts=True)
    color_variance = float(len(unique_counts)) / (img_array.shape[0] * img_array.shape[1])

    threshold = np.percentile(gradient_magnitude, 90)
    spiky_pixel_ratio = float(np.sum(gradient_magnitude > threshold) / gradient_magnitude.size)

    edge_score = 1.0 if edge_density > 500 else edge_density / 1000.0
    gradient_score = min(1.0, avg_gradient / 50.0)
    flat_color_score = 1.0 if color_variance < 0.01 else max(0.0, 1.0 - color_variance / 0.1)
    spiky_score = min(1.0, spiky_pixel_ratio * 5)
    total = 0.4 * edge_score + 0.3 * gradient_score + 0.2 * flat_color_score + 0.1 * spiky_score

    return total, {
        "edge_density": round(edge_density, 1),
        "avg_gradient": round(avg_gradient, 1),
        "high_contrast_ratio": round(high_contrast_ratio, 3),
        "color_variance": round(color_variance, 4),
        "spiky_pixel_ratio": round(spiky_pixel_ratio, 3),
    }


def _from_pil(img) -> tuple[str, float, dict, str]:
    import numpy as np
    arr = np.array(img.convert("RGB"))

    heur_score, heuristics = _heuristics(arr)
    is_manga_heur = heur_score > 0.6

    model = _load_model()
    model_used = "heuristics"
    if model is not None:
        import torch  # noqa: PLC0415
        img224 = img.convert("RGB").resize((224, 224))
        a = np.array(img224, dtype=np.float32) / 255.0
        a = (a - MEAN) / STD
        t = torch.from_numpy(a).permute(2, 0, 1).unsqueeze(0)
        with torch.no_grad():
            prob = float(torch.squeeze(model(t)).item())
        model_used = "cnn+heuristics"
        is_manga_model = prob > 0.5
        if is_manga_model == is_manga_heur:
            label = "manga" if is_manga_model else "not_manga"
            conf = prob if is_manga_model else 1 - prob
        elif is_manga_heur and not is_manga_model:
            label, conf = "manga", min(prob * 0.3 + 0.7, 1.0)
        elif is_manga_model and not is_manga_heur:
            label, conf = "manga", prob
        else:
            label, conf = "not_manga", 1 - prob
    else:
        label = "manga" if is_manga_heur else "not_manga"
        conf = max(0.5, min(heur_score, 0.85)) if is_manga_heur else max(0.5, min(1 - heur_score, 0.85))

    return label, round(conf, 4), heuristics, model_used


def classify_image_bytes(image_bytes: bytes) -> dict:
    """Classify a manga sketch from raw image bytes (png/jpg/webp)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        return {"status": "error", "error": f"could not read image: {type(e).__name__}: {e}"}
    label, conf, heur, used = _from_pil(img)
    return {
        "status": "ok",
        "label": label,
        "confidence": conf,
        "is_manga": label == "manga",
        "heuristics": heur,
        "model": used,
        "method": "sketch-recog port: ImprovedCNN + edge/gradient/flat-color heuristics (original agreement logic)",
    }


def classify_base64(b64: str) -> dict:
    """Strip a data: URL prefix if present, then classify."""
    if "," in b64 and b64.strip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        return classify_image_bytes(base64.b64decode(b64))
    except Exception as e:
        return {"status": "error", "error": f"invalid base64 image: {type(e).__name__}"}


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sketch-recog/sketch-recog/manga_model/data/val/manga/manga_0001.png"
    out = classify_image_bytes(Path(p).read_bytes())
    print(out["label"], out["confidence"], out["model"], out["heuristics"])
    p2 = "/tmp/sketch-recog/sketch-recog/manga_model/data/val/non_manga/non_manga_0001.png"
    out2 = classify_image_bytes(Path(p2).read_bytes())
    print(out2["label"], out2["confidence"], out2["model"])
