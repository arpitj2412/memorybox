from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import imagehash
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".bmp"}
HAMMING_THRESHOLD = 10
CLIP_RESPLIT_THRESHOLD = 15


@dataclass
class Photo:
    path: Path
    phash: object = None
    thumb: object = None  # PIL Image, loaded lazily


@dataclass
class PhotoGroup:
    photos: list[Photo] = field(default_factory=list)
    best: Optional[Photo] = None
    reason: str = ""
    user_override: bool = False

    @property
    def name(self) -> str:
        if not self.photos:
            return "Unknown"
        stems = [p.path.stem for p in self.photos]
        prefix = _common_prefix(stems)
        return prefix.rstrip("_- ") if len(prefix) > 2 else f"Scene {id(self) % 9999 + 1}"


def _common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def find_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def _compute_phash(photo: Photo) -> None:
    try:
        with Image.open(photo.path) as img:
            img = img.convert("RGB")
            photo.phash = imagehash.phash(img)
    except Exception:
        photo.phash = None


def _group_by_phash(photos: list[Photo], threshold: int = HAMMING_THRESHOLD) -> list[list[Photo]]:
    groups: list[list[Photo]] = []
    ungrouped = list(photos)

    while ungrouped:
        seed = ungrouped.pop(0)
        group = [seed]
        remaining = []
        for photo in ungrouped:
            if seed.phash is not None and photo.phash is not None:
                distance = seed.phash - photo.phash
                if distance <= threshold:
                    group.append(photo)
                    continue
            remaining.append(photo)
        ungrouped = remaining
        groups.append(group)

    return groups


def _clip_resplit(group: list[Photo]) -> list[list[Photo]]:
    """Re-split large groups using CLIP embeddings."""
    try:
        import open_clip
        import torch
        import numpy as np

        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model.eval()

        embeddings = []
        valid_photos = []
        for photo in group:
            try:
                with Image.open(photo.path) as img:
                    tensor = preprocess(img.convert("RGB")).unsqueeze(0)
                with torch.no_grad():
                    emb = model.encode_image(tensor)
                    emb = emb / emb.norm(dim=-1, keepdim=True)
                embeddings.append(emb.squeeze(0).numpy())
                valid_photos.append(photo)
            except Exception:
                continue

        if len(valid_photos) < 2:
            return [group]

        embeddings = np.array(embeddings)
        # Simple greedy clustering by cosine similarity threshold 0.85
        clusters: list[list[Photo]] = []
        used = [False] * len(valid_photos)

        for i, photo in enumerate(valid_photos):
            if used[i]:
                continue
            cluster = [photo]
            used[i] = True
            for j in range(i + 1, len(valid_photos)):
                if used[j]:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]))
                if sim >= 0.85:
                    cluster.append(valid_photos[j])
                    used[j] = True
            clusters.append(cluster)

        return clusters if clusters else [group]

    except Exception:
        # CLIP not available or failed — return original group unsplit
        return [group]


def group_photos(
    folder: Path,
    threshold: int = HAMMING_THRESHOLD,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[PhotoGroup]:
    images = find_images(folder)
    total = len(images)

    photos = [Photo(path=p) for p in images]

    for i, photo in enumerate(photos):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Cancelled")
        _compute_phash(photo)
        if progress_callback:
            progress_callback(i + 1, total, f"Hashing {photo.path.name}")

    raw_groups = _group_by_phash(photos, threshold)

    # Re-split large groups
    final_photo_lists: list[list[Photo]] = []
    for g in raw_groups:
        if len(g) > CLIP_RESPLIT_THRESHOLD:
            sub = _clip_resplit(g)
            final_photo_lists.extend(sub)
        else:
            final_photo_lists.append(g)

    groups = []
    for photo_list in final_photo_lists:
        pg = PhotoGroup(photos=photo_list)
        if photo_list:
            pg.best = photo_list[0]  # scorer will override this
        groups.append(pg)

    return groups
