from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Callable, Optional

import anthropic
from PIL import Image

from app.core.grouper import Photo, PhotoGroup


SCORE_PROMPT = """You are a professional photo curator. I will show you a set of photos from the same burst or scene.
Select the single best photo based on: sharpness, exposure, composition, expressions (if people), and overall quality.

Reply with ONLY a JSON object in this exact format (no markdown):
{"best_index": <0-based index>, "reason": "<one short sentence explaining why>"}"""

MAX_IMAGE_PIXELS = 1024  # resize to fit within this box before sending


def _encode_image(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type) resized to fit MAX_IMAGE_PIXELS."""
    suffix = path.suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".heic": "image/jpeg", ".heif": "image/jpeg",
        ".tiff": "image/jpeg", ".tif": "image/jpeg", ".bmp": "image/jpeg",
    }
    media_type = media_map.get(suffix, "image/jpeg")

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_PIXELS, MAX_IMAGE_PIXELS), Image.LANCZOS)
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = base64.b64encode(buf.getvalue()).decode()

    return data, "image/jpeg"


def score_groups(
    groups: list[PhotoGroup],
    api_key: str,
    batch_size: int = 8,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[PhotoGroup]:
    client = anthropic.Anthropic(api_key=api_key)
    total = len(groups)

    for i, group in enumerate(groups):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Cancelled")

        group_name = group.name
        if progress_callback:
            progress_callback(i, total, f"Scoring {group_name}")

        if len(group.photos) == 1:
            group.best = group.photos[0]
            group.reason = "Only photo in group."
            if progress_callback:
                progress_callback(i + 1, total, group_name)
            continue

        # Send up to batch_size photos at once to Claude
        photos_to_score = group.photos[:batch_size]

        content: list[dict] = []
        for idx, photo in enumerate(photos_to_score):
            try:
                data, media_type = _encode_image(photo.path)
                content.append({
                    "type": "text",
                    "text": f"Photo {idx} ({photo.path.name}):"
                })
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data}
                })
            except Exception as e:
                content.append({"type": "text", "text": f"Photo {idx}: [failed to load: {e}]"})

        content.append({"type": "text", "text": SCORE_PROMPT})

        try:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=256,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()
            import json
            result = json.loads(raw)
            best_idx = int(result.get("best_index", 0))
            best_idx = max(0, min(best_idx, len(photos_to_score) - 1))
            group.best = photos_to_score[best_idx]
            group.reason = result.get("reason", "")
        except Exception as e:
            group.best = group.photos[0]
            group.reason = f"Scoring failed: {e}"

        if progress_callback:
            progress_callback(i + 1, total, group_name)

    return groups
