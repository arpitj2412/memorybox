from __future__ import annotations

import queue
import threading
import tempfile
import shutil
from pathlib import Path
from typing import Callable

import customtkinter as ctk

ACCENT = "#7F77DD"


class ProgressView(ctk.CTkFrame):
    def __init__(self, master, config: dict, on_done: Callable, on_cancel: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._config = config
        self._on_done = on_done
        self._on_cancel = on_cancel
        self._queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._temp_dir: str | None = None
        self._build()
        self._start_worker()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="MemoryBox", font=("", 22, "bold"),
                     text_color=ACCENT).grid(row=0, column=0, pady=(28, 4))

        self._phase_label = ctk.CTkLabel(self, text="Starting...", font=("", 14))
        self._phase_label.grid(row=1, column=0, pady=(0, 8))

        self._progress_bar = ctk.CTkProgressBar(self, width=560, progress_color=ACCENT)
        self._progress_bar.grid(row=2, column=0, padx=60, pady=(0, 6))
        self._progress_bar.set(0)

        self._sub_label = ctk.CTkLabel(self, text="", font=("", 11), text_color="gray")
        self._sub_label.grid(row=3, column=0, pady=(0, 12))

        # Scrollable log box
        log_frame = ctk.CTkFrame(self, fg_color="#0f0f1e", corner_radius=8)
        log_frame.grid(row=4, column=0, sticky="nsew", padx=40, pady=(0, 12))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._log_text = ctk.CTkTextbox(log_frame, font=("Menlo", 11), wrap="word",
                                        fg_color="#0f0f1e", text_color="#aaffaa",
                                        state="disabled")
        self._log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self._cancel_btn = ctk.CTkButton(self, text="Cancel", width=120,
                                         fg_color="#444466", hover_color="#333355",
                                         command=self._request_cancel)
        self._cancel_btn.grid(row=5, column=0, pady=(0, 20))

        self._poll_queue()

    def _append_log(self, text: str):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", text + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_message(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "phase":
            self._phase_label.configure(text=msg["text"])
        elif mtype == "progress":
            self._progress_bar.set(msg["value"])
            self._sub_label.configure(text=msg.get("sub", ""))
        elif mtype == "log":
            self._append_log(msg["text"])
        elif mtype == "done":
            self._on_done(msg.get("stats", {}), msg.get("groups", []))
        elif mtype == "error":
            self._phase_label.configure(text="Error", text_color="red")
            self._append_log(f"ERROR: {msg['text']}")
            self._cancel_btn.configure(text="Back", command=self._on_cancel)

    def _request_cancel(self):
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled", text="Cancelling...")

    def _start_worker(self):
        thread = threading.Thread(target=self._worker, daemon=True)
        thread.start()

    def _worker(self):
        from app.core.grouper import group_photos
        from app.core.scorer import score_groups
        from app.core.output import copy_keepers, generate_report

        config = self._config
        input_folder: Path = config["input_folder"]
        output_folder: Path = config["output_folder"]
        threshold: float = config["threshold"]
        batch_size: int = config["batch_size"]
        generate_report_flag: bool = config["generate_report"]
        api_key: str = config["api_key"]

        self._temp_dir = tempfile.mkdtemp(prefix="memorybox_")
        groups = []

        try:
            # Phase 1: Grouping
            self._queue.put({"type": "phase", "text": "Grouping photos..."})

            def group_progress(current, total, message):
                if self._cancel_event.is_set():
                    raise InterruptedError("Cancelled")
                pct = current / total if total else 0
                self._queue.put({
                    "type": "progress",
                    "value": pct * 0.33,
                    "sub": f"Photo {current} of {total} — {message}"
                })

            groups = group_photos(
                input_folder,
                time_gap_seconds=int(threshold),
                progress_callback=group_progress,
                cancel_event=self._cancel_event,
            )

            total_photos = sum(len(g.photos) for g in groups)
            self._queue.put({"type": "log", "text": f"Found {total_photos} photos in {len(groups)} groups."})

            # Phase 2: AI Scoring
            self._queue.put({"type": "phase", "text": "Scoring with AI..."})

            def score_progress(current, total, group_name):
                if self._cancel_event.is_set():
                    raise InterruptedError("Cancelled")
                base = 0.33
                pct = current / total if total else 0
                self._queue.put({
                    "type": "progress",
                    "value": base + pct * 0.50,
                    "sub": f"Group {current} of {total} — sending to Claude..."
                })
                self._queue.put({"type": "log", "text": f"Group {current}: {group_name} — scored."})

            groups = score_groups(
                groups,
                api_key=api_key,
                batch_size=batch_size,
                progress_callback=score_progress,
                cancel_event=self._cancel_event,
            )

            # Phase 3: Copying keepers
            self._queue.put({"type": "phase", "text": "Copying keepers..."})

            def copy_progress(current, total, name):
                base = 0.83
                pct = current / total if total else 0
                self._queue.put({
                    "type": "progress",
                    "value": base + pct * 0.10,
                    "sub": f"Copying {current} of {total}..."
                })

            copy_keepers(groups, output_folder, progress_callback=copy_progress)

            # Phase 4: Optional HTML report
            if generate_report_flag and not self._cancel_event.is_set():
                self._queue.put({"type": "phase", "text": "Generating report..."})
                self._queue.put({"type": "progress", "value": 0.95, "sub": "Writing HTML..."})
                generate_report(groups, output_folder)
                self._queue.put({"type": "log", "text": "HTML report saved to output folder."})

            self._queue.put({"type": "progress", "value": 1.0, "sub": "Done!"})

            total_photos = sum(len(g.photos) for g in groups)
            duplicates = total_photos - len(groups)
            stats = {
                "total_photos": total_photos,
                "unique_scenes": len(groups),
                "duplicates_removed": duplicates,
            }
            self._queue.put({"type": "done", "stats": stats, "groups": groups})

        except InterruptedError:
            self._queue.put({"type": "log", "text": "Processing cancelled."})
            self._queue.put({"type": "phase", "text": "Cancelled"})
            # Clean up and return to home
            self.after(800, self._on_cancel)
        except Exception as e:
            self._queue.put({"type": "error", "text": str(e)})
        finally:
            if self._temp_dir:
                try:
                    shutil.rmtree(self._temp_dir, ignore_errors=True)
                except Exception:
                    pass
