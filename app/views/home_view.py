from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import keyring

ACCENT = "#7F77DD"
KEYRING_SERVICE = "memorybox"
KEYRING_USER = "anthropic_api_key"


class HomeView(ctk.CTkFrame):
    def __init__(self, master, on_run=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_run = on_run
        self._build()
        self._load_saved_key()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(self, text="MemoryBox", font=("", 28, "bold")).grid(
            row=0, column=0, pady=(28, 2))
        ctk.CTkLabel(self, text="Pick the best. Skip the rest.",
                     font=("", 13), text_color="gray").grid(row=1, column=0, pady=(0, 16))

        # Divider
        ctk.CTkFrame(self, height=1, fg_color="#333355").grid(
            row=2, column=0, sticky="ew", padx=40, pady=(0, 20))

        # Input folder row
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=3, column=0, sticky="ew", padx=40, pady=(0, 4))
        input_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(input_frame, text="Photos folder", width=120, anchor="w").grid(
            row=0, column=0, padx=(0, 8))
        self._input_var = tk.StringVar()
        ctk.CTkEntry(input_frame, textvariable=self._input_var, state="disabled",
                     width=360).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(input_frame, text="Browse", width=80,
                      command=self._browse_input).grid(row=0, column=2)
        self._input_error = ctk.CTkLabel(self, text="", text_color="red", font=("", 11))
        self._input_error.grid(row=4, column=0, sticky="w", padx=162)

        # Output folder row
        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.grid(row=5, column=0, sticky="ew", padx=40, pady=(4, 4))
        out_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out_frame, text="Output folder", width=120, anchor="w").grid(
            row=0, column=0, padx=(0, 8))
        self._output_var = tk.StringVar()
        ctk.CTkEntry(out_frame, textvariable=self._output_var, state="disabled",
                     width=360).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(out_frame, text="Browse", width=80,
                      command=self._browse_output).grid(row=0, column=2)
        self._output_error = ctk.CTkLabel(self, text="", text_color="red", font=("", 11))
        self._output_error.grid(row=6, column=0, sticky="w", padx=162)

        # Settings section (collapsible)
        self._settings_visible = False
        self._settings_toggle = ctk.CTkButton(
            self, text="Settings ▸", width=120, fg_color="transparent",
            text_color=ACCENT, hover_color="#222244", anchor="w",
            command=self._toggle_settings)
        self._settings_toggle.grid(row=7, column=0, sticky="w", padx=40, pady=(8, 0))

        self._settings_frame = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=10)
        # Hidden by default — placed in grid row 8 but not shown

        # Time gap slider
        sf = self._settings_frame
        sf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sf, text="Time gap (seconds)", anchor="w").grid(
            row=0, column=0, padx=16, pady=(12, 4), sticky="w")
        self._threshold_var = tk.DoubleVar(value=60)
        self._threshold_label = ctk.CTkLabel(sf, text="60s", width=40)
        self._threshold_label.grid(row=0, column=2, padx=16)
        ctk.CTkSlider(sf, from_=10, to=300, variable=self._threshold_var,
                      command=self._on_threshold_change, width=240).grid(
            row=0, column=1, padx=8, pady=(12, 4))

        # Batch size
        ctk.CTkLabel(sf, text="Batch size", anchor="w").grid(
            row=1, column=0, padx=16, pady=4, sticky="w")
        self._batch_var = tk.StringVar(value="8")
        ctk.CTkSegmentedButton(sf, values=["4", "8", "12"],
                               variable=self._batch_var).grid(
            row=1, column=1, padx=8, pady=4, sticky="w")

        # HTML report checkbox
        self._report_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(sf, text="Generate HTML report",
                        variable=self._report_var).grid(
            row=2, column=0, columnspan=3, padx=16, pady=(4, 12), sticky="w")

        # API key row
        api_frame = ctk.CTkFrame(self, fg_color="transparent")
        api_frame.grid(row=9, column=0, sticky="ew", padx=40, pady=(12, 0))
        api_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(api_frame, text="Anthropic API Key", width=120, anchor="w").grid(
            row=0, column=0, padx=(0, 8))
        self._api_var = tk.StringVar()
        self._api_entry = ctk.CTkEntry(api_frame, textvariable=self._api_var,
                                       show="•", width=360)
        self._api_entry.grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(api_frame, text="?", width=32, fg_color="#333355",
                      command=self._show_api_help).grid(row=0, column=2)
        self._api_error = ctk.CTkLabel(self, text="", text_color="red", font=("", 11))
        self._api_error.grid(row=10, column=0, sticky="w", padx=162)

        self._api_var.trace_add("write", lambda *_: self._update_run_button())

        # Run button
        self._run_btn = ctk.CTkButton(
            self, text="Analyse Photos →", height=44,
            fg_color=ACCENT, hover_color="#6B63CC",
            font=("", 15, "bold"), state="disabled",
            command=self._on_run_clicked)
        self._run_btn.grid(row=11, column=0, sticky="ew", padx=40, pady=(20, 8))

        # Status bar
        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(self, textvariable=self._status_var,
                     text_color="gray", font=("", 11)).grid(
            row=12, column=0, pady=(0, 12))

    def _load_saved_key(self):
        # Try env var first, then keyring
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            self._api_var.set(env_key)
            self._update_run_button()
            return
        try:
            saved = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if saved:
                self._api_var.set(saved)
                self._update_run_button()
        except Exception:
            pass

    def _toggle_settings(self):
        self._settings_visible = not self._settings_visible
        if self._settings_visible:
            self._settings_frame.grid(row=8, column=0, sticky="ew", padx=40, pady=(4, 0))
            self._settings_toggle.configure(text="Settings ▾")
        else:
            self._settings_frame.grid_forget()
            self._settings_toggle.configure(text="Settings ▸")

    def _on_threshold_change(self, val):
        self._threshold_label.configure(text=f"{int(float(val))}s")

    def _browse_input(self):
        folder = filedialog.askdirectory(title="Select photos folder")
        if folder:
            self._set_entry(self._input_var, folder)
            self._input_error.configure(text="")
            # Auto-populate output
            if not self._output_var.get():
                self._set_entry(self._output_var, folder + "_best")
            self._update_run_button()

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._set_entry(self._output_var, folder)
            self._output_error.configure(text="")
            self._update_run_button()

    def _set_entry(self, var: tk.StringVar, value: str):
        var.set(value)

    def _show_api_help(self):
        messagebox.showinfo(
            "Anthropic API Key",
            "Get your key at: console.anthropic.com\n\nThe key starts with 'sk-ant-'.\nIt will be stored securely in your macOS Keychain."
        )

    def _validate(self) -> bool:
        valid = True

        input_path = Path(self._input_var.get()) if self._input_var.get() else None
        if not input_path or not input_path.exists():
            self._input_error.configure(text="Folder does not exist.")
            valid = False
        else:
            from app.core.grouper import IMAGE_EXTENSIONS
            images = [p for p in input_path.iterdir()
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
            if not images:
                self._input_error.configure(text="No image files found in folder.")
                valid = False
            else:
                self._input_error.configure(text="")

        output_str = self._output_var.get()
        if not output_str:
            self._output_error.configure(text="Please choose an output folder.")
            valid = False
        else:
            try:
                out_path = Path(output_str)
                out_path.mkdir(parents=True, exist_ok=True)
                self._output_error.configure(text="")
            except Exception:
                self._output_error.configure(text="Cannot write to this location.")
                valid = False

        api_key = self._api_var.get().strip()
        if not api_key.startswith("sk-ant-"):
            self._api_error.configure(text="Key must start with 'sk-ant-'.")
            valid = False
        else:
            self._api_error.configure(text="")

        return valid

    def _update_run_button(self):
        has_input = bool(self._input_var.get())
        has_output = bool(self._output_var.get())
        has_key = bool(self._api_var.get().strip())
        state = "normal" if (has_input and has_output and has_key) else "disabled"
        self._run_btn.configure(state=state)

    def _on_run_clicked(self):
        if not self._validate():
            return

        api_key = self._api_var.get().strip()
        # Save to keyring
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, api_key)
        except Exception:
            pass

        config = {
            "input_folder": Path(self._input_var.get()),
            "output_folder": Path(self._output_var.get()),
            "threshold": int(self._threshold_var.get()),
            "batch_size": int(self._batch_var.get()),
            "generate_report": self._report_var.get(),
            "api_key": api_key,
        }

        if self._on_run:
            self._on_run(config)

    def set_status(self, text: str):
        self._status_var.set(text)
