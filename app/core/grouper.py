from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import imagehash
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".bmp"}
DEFAULT_TIME_GAP_SECONDS = 60
HAMMING_THRESHOLD = 10          # fallback when no EXIF
CLIP_RESPLIT_THRESHOLD = 30


@dataclass
class Photo:
    path: Path
    timestamp: Optional[datetime] = None
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
        return prefix.rstrip("_- ") if len(prefix) > 2 else f"Scene {abs(hash(self.photos[0].path.name)) % 9999 + 1}"


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


def _read_exif_timestamp(path: Path) -> Optional[datetime]:
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif:
                return None
            raw = exif.get(36867) or exif.get(306)  # DateTimeOriginal or DateTime
            if raw:
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _compute_phash(photo: Photo) -> None:
    try:
        with Image.open(photo.path) as img:
            photo.phash = imagehash.phash(img.convert("RGB"))
    except Exception:
        photo.phash = None


def _group_by_time(photos: list[Photo], gap_seconds: int) -> list[list[Photo]]:
    """Group consecutive photos where the time gap between neighbours <= gap_seconds."""
    if not photos:
        return []
    sorted_photos = sorted(photos, key=lambda p: p.timestamp or datetime.min)
    groups: list[list[Photo]] = [[sorted_photos[0]]]
    for photo in sorted_photos[1:]:
        prev = groups[-1][-1]
        if (photo.timestamp and prev.timestamp and
                (photo.timestamp - prev.timestamp).total_seconds() <= gap_seconds):
            groups[-1].append(photo)
        else:
            groups.append([photo])
    return groups


def _group_by_phash(photos: list[Photo], threshold: int = HAMMING_THRESHOLD) -> list[list[Photo]]:
    groups: list[list[Photo]] = []
    ungrouped = list(photos)
    while ungrouped:
        seed = ungrouped.pop(0)
        group = [seed]
        remaining = []
        for photo in ungrouped:
            if (seed.phash is not None and photo.phash is not None and
                    seed.phash - photo.phash <= threshold):
                group.append(photo)
            else:
                remaining.append(photo)
        ungrouped = remaining
        groups.append(group)
    return groups


def _clip_resplit(group: list[Photo]) -> list[list[Photo]]:
    try:
        import open_clip
        import torch
        import numpy as np

        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model.eval()

        embeddings, valid_photos = [], []
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
        clusters: list[list[Photo]] = []
        used = [False] * len(valid_photos)
        for i, photo in enumerate(valid_photos):
            if used[i]:
                continue
            cluster = [photo]
            used[i] = True
            for j in range(i + 1, len(valid_photos)):
                if not used[j] and float(np.dot(embeddings[i], embeddings[j])) >= 0.85:
                    cluster.append(valid_photos[j])
                    used[j] = True
            clusters.append(cluster)
        return clusters or [group]
    except Exception:
        return [group]


def group_photos(
    folder: Path,
    time_gap_seconds: int = DEFAULT_TIME_GAP_SECONDS,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[PhotoGroup]:
    image_paths = find_images(folder)
    total = len(image_paths)
    photos: list[Photo] = []

    for i, path in enumerate(image_paths):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Cancelled")
        ts = _read_exif_timestamp(path)
        photo = Photo(path=path, timestamp=ts)
        photos.append(photo)
        if progress_callback:
            progress_callback(i + 1, total, path.name)

    has_exif = sum(1 for p in photos if p.timestamp is not None)

    if has_exif >= len(photos) * 0.5:
        # Primary path: time-based grouping
        raw_groups = _group_by_time(photos, time_gap_seconds)
    else:
        # Fallback: pHash grouping for photos without timestamps
        for photo in photos:
            _compute_phash(photo)
        raw_groups = _group_by_phash(photos)

    # Re-split very large groups with CLIP
    final_lists: list[list[Photo]] = []
    for g in raw_groups:
        if len(g) > CLIP_RESPLIT_THRESHOLD:
            final_lists.extend(_clip_resplit(g))
        else:
            final_lists.append(g)

    groups = []
    for photo_list in final_lists:
        pg = PhotoGroup(photos=photo_list)
        if photo_list:
            pg.best = photo_list[0]
        groups.append(pg)

    return groups
