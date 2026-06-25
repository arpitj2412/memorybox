from __future__ import annotations

import base64
import io
import shutil
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from app.core.grouper import PhotoGroup


def copy_keepers(
    groups: list[PhotoGroup],
    output_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(groups)

    for i, group in enumerate(groups):
        if group.best:
            dest = output_dir / group.best.path.name
            # Avoid overwriting if duplicate filenames
            if dest.exists():
                dest = output_dir / f"{dest.stem}_{i}{dest.suffix}"
            shutil.copy2(group.best.path, dest)
        if progress_callback:
            progress_callback(i + 1, total, group.name)


def _thumb_b64(path: Path, size: tuple[int, int] = (300, 225)) -> str:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail(size, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def generate_report(
    groups: list[PhotoGroup],
    output_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(groups)
    cards_html = []

    for i, group in enumerate(groups):
        best = group.best
        if not best:
            continue

        best_b64 = _thumb_b64(best.path)
        best_img = f'<img src="data:image/jpeg;base64,{best_b64}" class="best-thumb" />' if best_b64 else ""

        others_html = ""
        for photo in group.photos:
            if photo is best:
                continue
            b64 = _thumb_b64(photo.path, (120, 90))
            if b64:
                others_html += f'<img src="data:image/jpeg;base64,{b64}" class="strip-thumb" title="{photo.path.name}" />'

        override_badge = '<span class="badge override">✏ Overridden</span>' if group.user_override else ""
        reason_text = group.reason or ""

        cards_html.append(f"""
        <div class="card">
            <div class="best-wrap">
                {best_img}
                <span class="badge best">✓ Best pick</span>
                {override_badge}
            </div>
            <div class="group-name">{group.name}</div>
            <div class="reason">{reason_text}</div>
            <div class="strip">{others_html}</div>
        </div>
        """)

        if progress_callback:
            progress_callback(i + 1, total, group.name)

    total_photos = sum(len(g.photos) for g in groups)
    duplicates = total_photos - len(groups)
    pct = int(duplicates / total_photos * 100) if total_photos else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MemoryBox Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }}
  h1 {{ color: #7F77DD; }}
  .stats {{ display: flex; gap: 12px; margin-bottom: 24px; }}
  .pill {{ background: #2a2a4a; border-radius: 20px; padding: 6px 16px; font-size: 13px; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
  .card {{ background: #16213e; border-radius: 12px; padding: 14px; }}
  .best-wrap {{ position: relative; display: inline-block; }}
  .best-thumb {{ width: 100%; max-width: 300px; height: 200px; object-fit: cover; border-radius: 8px; display: block; }}
  .badge {{ position: absolute; top: 8px; left: 8px; background: #22c55e; color: #fff;
            font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 10px; }}
  .badge.override {{ background: #f59e0b; left: auto; right: 8px; }}
  .group-name {{ font-weight: bold; margin: 8px 0 4px; font-size: 13px; }}
  .reason {{ font-size: 12px; color: #aaa; margin-bottom: 8px;
             overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
  .strip {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .strip-thumb {{ width: 80px; height: 60px; object-fit: cover; border-radius: 4px; cursor: pointer; opacity: 0.7; }}
  .strip-thumb:hover {{ opacity: 1; }}
</style>
</head>
<body>
<h1>MemoryBox Report</h1>
<div class="stats">
  <span class="pill">{total_photos} photos in</span>
  <span class="pill">{len(groups)} unique scenes</span>
  <span class="pill">{duplicates} duplicates removed ({pct}%)</span>
</div>
<div class="grid">
  {''.join(cards_html)}
</div>
</body>
</html>"""

    report_path = output_dir / "memorybox_report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
