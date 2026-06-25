from __future__ import annotations

import subprocess
import webbrowser
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

from app.core.grouper import PhotoGroup

ACCENT = "#7F77DD"
THUMB_CACHE_MAX = 200


class ThumbnailCache:
    def __init__(self, max_size: int = THUMB_CACHE_MAX):
        self._cache: OrderedDict[str, ctk.CTkImage] = OrderedDict()
        self._max = max_size

    def get(self, path: Path, size: tuple[int, int]) -> ctk.CTkImage | None:
        key = f"{path}:{size}"
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, path: Path, size: tuple[int, int], img: ctk.CTkImage):
        key = f"{path}:{size}"
        self._cache[key] = img
        self._cache.move_to_end(key)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)

    def load(self, path: Path, size: tuple[int, int]) -> ctk.CTkImage | None:
        cached = self.get(path, size)
        if cached:
            return cached
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail(size, Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self.put(path, size, ctk_img)
                return ctk_img
        except Exception:
            return None


_thumb_cache = ThumbnailCache()


class GroupCard(ctk.CTkFrame):
    def __init__(self, master, group: PhotoGroup, index: int, **kwargs):
        super().__init__(master, fg_color="#16213e", corner_radius=12, **kwargs)
        self._group = group
        self._index = index
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Best pick thumbnail
        best_img = _thumb_cache.load(self._group.best.path, (200, 150)) if self._group.best else None
        self._best_label = ctk.CTkLabel(self, image=best_img, text="",
                                        width=200, height=150)
        self._best_label.grid(row=0, column=0, padx=12, pady=(12, 0), sticky="w")

        # Best pick badge
        badge = ctk.CTkLabel(self, text="✓ Best pick", font=("", 11, "bold"),
                             fg_color="#22c55e", corner_radius=8,
                             text_color="white", width=72, height=22)
        badge.place(in_=self._best_label, anchor="nw", x=8, y=8)

        # Override badge (shown when user overrides)
        self._override_badge = ctk.CTkLabel(self, text="✏ Overridden", font=("", 10, "bold"),
                                            fg_color="#f59e0b", corner_radius=8,
                                            text_color="white", width=80, height=22)
        if self._group.user_override:
            self._override_badge.place(in_=self._best_label, anchor="ne", x=-8, y=8)

        # Group name
        ctk.CTkLabel(self, text=self._group.name, font=("", 13, "bold"),
                     anchor="w").grid(row=1, column=0, padx=12, pady=(6, 2), sticky="w")

        # AI reason
        reason = self._group.reason or ""
        if len(reason) > 100:
            reason = reason[:100] + "…"
        ctk.CTkLabel(self, text=reason, font=("", 12), text_color="gray",
                     anchor="w", wraplength=180, justify="left").grid(
            row=2, column=0, padx=12, pady=(0, 6), sticky="w")

        # Strip of other thumbnails
        others = [p for p in self._group.photos if p is not self._group.best]
        if others:
            strip_frame = ctk.CTkFrame(self, fg_color="transparent")
            strip_frame.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="w")
            for i, photo in enumerate(others[:8]):  # show max 8 in strip
                thumb = _thumb_cache.load(photo.path, (48, 36))
                btn = ctk.CTkButton(
                    strip_frame, image=thumb, text="", width=48, height=36,
                    fg_color="#0f0f1e", hover_color="#222244", corner_radius=4,
                    command=lambda p=photo: self._swap_best(p)
                )
                btn.grid(row=0, column=i, padx=2)

    def _swap_best(self, photo):
        self._group.best = photo
        self._group.user_override = True
        # Reload card
        for widget in self.winfo_children():
            widget.destroy()
        self._build()


class ResultsView(ctk.CTkFrame):
    def __init__(self, master, stats: dict, groups: list[PhotoGroup],
                 output_folder: Path, on_start_over: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._stats = stats
        self._groups = groups
        self._output_folder = output_folder
        self._on_start_over = on_start_over
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Stats bar
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))

        total = self._stats.get("total_photos", 0)
        scenes = self._stats.get("unique_scenes", 0)
        dupes = self._stats.get("duplicates_removed", 0)
        pct = int(dupes / total * 100) if total else 0

        for i, (text, color) in enumerate([
            (f"{total} photos in", ACCENT),
            (f"{scenes} unique scenes", "#22c55e"),
            (f"{dupes} duplicates removed ({pct}%)", "#f59e0b"),
        ]):
            ctk.CTkLabel(stats_frame, text=text, fg_color="#2a2a4a",
                         corner_radius=16, font=("", 12),
                         padx=14, pady=6).grid(row=0, column=i, padx=6)

        # Scrollable grid of group cards
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="#0f0f1e", corner_radius=8)
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        self._scroll.grid_columnconfigure((0, 1), weight=1)

        for i, group in enumerate(self._groups):
            if not group.best:
                continue
            card = GroupCard(self._scroll, group, i)
            card.grid(row=i // 2, column=i % 2, padx=10, pady=10, sticky="nsew")

        # Button row
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=(4, 16))

        ctk.CTkButton(btn_frame, text="Open Output Folder", width=160,
                      fg_color="#333355", hover_color="#444477",
                      command=self._open_output).grid(row=0, column=0, padx=8)

        ctk.CTkButton(btn_frame, text="Save HTML Report", width=150,
                      fg_color="#333355", hover_color="#444477",
                      command=self._save_report).grid(row=0, column=1, padx=8)

        ctk.CTkButton(btn_frame, text="Start Over", width=110,
                      fg_color=ACCENT, hover_color="#6B63CC",
                      command=self._on_start_over).grid(row=0, column=2, padx=8)

    def _open_output(self):
        subprocess.run(["open", str(self._output_folder)], check=False)

    def _save_report(self):
        from app.core.output import generate_report
        report_path = generate_report(self._groups, self._output_folder)
        webbrowser.open(report_path.as_uri())
