from __future__ import annotations

import math
from io import BytesIO
from typing import Protocol

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.triage.contracts import VISIBLE_CLASS_ORDER, ImageQuality, VisionPrediction

VISION_MODEL_VERSION = "vision-pillow-demo-1.0.0"
ALLOWED_MIME = {"image/jpeg": "JPEG", "image/png": "PNG"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_BYTES = 128
Image.MAX_IMAGE_PIXELS = 25_000_000


class ImageRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def sanitize_image(content: bytes, mime_type: str) -> bytes:
    if mime_type not in ALLOWED_MIME:
        raise ImageRejected("UNSUPPORTED_MEDIA", "Only JPEG and PNG are supported")
    if len(content) < MIN_IMAGE_BYTES or len(content) > MAX_IMAGE_BYTES:
        raise ImageRejected("INVALID_IMAGE_SIZE", "Image size is outside the accepted range")
    try:
        with Image.open(BytesIO(content)) as probe:
            probe.verify()
        with Image.open(BytesIO(content)) as source:
            clean = ImageOps.exif_transpose(source)
            output = BytesIO()
            image_format = ALLOWED_MIME[mime_type]
            if image_format == "JPEG" and clean.mode not in {"RGB", "L"}:
                clean = clean.convert("RGB")
            clean.save(output, format=image_format, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageRejected("INVALID_IMAGE", "Uploaded content is not a safe image") from exc


def assess_quality(content: bytes) -> ImageQuality:
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            gray = image.convert("L")
            brightness = ImageStat.Stat(gray).mean[0]
            edges = gray.filter(ImageFilter.FIND_EDGES)
            margin_x = max(1, width // 20)
            margin_y = max(1, height // 20)
            interior = edges.crop((margin_x, margin_y, width - margin_x, height - margin_y))
            edge_variance = ImageStat.Stat(interior).var[0]
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageRejected("INVALID_IMAGE", "Image cannot be decoded safely") from exc

    blur_score = min(1.0, edge_variance / 300.0)
    exposure_score = max(0.0, 1.0 - abs(brightness - 127.5) / 127.5)
    reasons = []
    if width < 128 or height < 128:
        reasons.append("RESOLUTION_TOO_LOW")
    if blur_score < 0.08:
        reasons.append("IMAGE_TOO_BLURRY")
    if brightness < 20:
        reasons.append("IMAGE_UNDEREXPOSED")
    if brightness > 235:
        reasons.append("IMAGE_OVEREXPOSED")
    resolution_score = min(1.0, min(width, height) / 512.0)
    score = round(0.4 * resolution_score + 0.3 * blur_score + 0.3 * exposure_score, 6)
    return ImageQuality(
        accepted=not reasons,
        score=score,
        width=width,
        height=height,
        blur_score=round(blur_score, 6),
        exposure_score=round(exposure_score, 6),
        rejection_reasons=reasons,
    )


class VisionAdapter(Protocol):
    version: str

    def predict(self, content: bytes) -> VisionPrediction: ...


class DeterministicVisionAdapter:
    """Contract-complete visual demo; these are not clinical probabilities."""

    version = VISION_MODEL_VERSION

    def predict(self, content: bytes) -> VisionPrediction:
        quality = assess_quality(content)
        if not quality.accepted:
            raise ImageRejected("IMAGE_QUALITY_REJECTED", ",".join(quality.rejection_reasons))
        with Image.open(BytesIO(content)) as source:
            stats = ImageStat.Stat(source.convert("RGB").resize((64, 64)))
            red, green, blue = (value / 255.0 for value in stats.mean)
            variance = sum(stats.var) / (3 * 255.0**2)
        raw = [
            0.12 + 0.35 * max(0.0, red - green),
            0.1 + 0.25 * max(0.0, blue - green),
            0.1 + 0.2 * variance,
            0.18 + 0.25 * green,
            0.18 + 0.25 * (1.0 - quality.score),
        ]
        total = sum(raw)
        probabilities = [round(value / total, 8) for value in raw]
        probabilities[-1] = round(1.0 - sum(probabilities[:-1]), 8)
        entropy = -sum(value * math.log(value) for value in probabilities if value > 0)
        uncertainty = min(1.0, entropy / math.log(len(probabilities)))
        uncertain = uncertainty >= 0.72 or max(probabilities) < 0.45
        if uncertain and probabilities[-1] < 0.2:
            shift = 0.2 - probabilities[-1]
            largest = max(range(len(probabilities) - 1), key=probabilities.__getitem__)
            probabilities[largest] -= shift
            probabilities[-1] = 0.2
        return VisionPrediction(
            class_order=VISIBLE_CLASS_ORDER,
            probabilities=probabilities,
            quality=quality,
            uncertainty=round(uncertainty, 6),
            uncertain=uncertain,
            model_version=self.version,
            calibration_status="DEMO_UNVALIDATED",
        )


class UnavailableVisionAdapter:
    version = "vision-unavailable"

    def predict(self, content: bytes) -> VisionPrediction:
        del content
        raise RuntimeError("VISION_MODEL_UNAVAILABLE")
