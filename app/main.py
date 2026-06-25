from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from app.views.home_view import HomeView


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MemoryBox")
        self.resizable(False, False)

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 720) // 2
        y = (self.winfo_screenheight() - 560) // 2
        self.geometry(f"720x560+{x}+{y}")

        self._current_view = None
        self._show_home()

    def _clear(self):
        if self._current_view:
            self._current_view.pack_forget()
            self._current_view.destroy()
            self._current_view = None

    def _show_home(self, last_status: str = "Ready"):
        self._clear()
        view = HomeView(self, on_run=self._on_run)
        view.pack(fill="both", expand=True)
        view.set_status(last_status)
        self._current_view = view

    def _on_run(self, config: dict):
        from app.views.progress_view import ProgressView
        self._clear()
        view = ProgressView(
            self,
            config=config,
            on_done=lambda stats, groups: self._on_done(stats, groups, config["output_folder"]),
            on_cancel=self._show_home,
        )
        view.pack(fill="both", expand=True)
        self._current_view = view

    def _on_done(self, stats: dict, groups: list, output_folder: Path):
        from app.views.results_view import ResultsView
        self._clear()
        view = ResultsView(
            self,
            stats=stats,
            groups=groups,
            output_folder=output_folder,
            on_start_over=self._show_home,
        )
        view.pack(fill="both", expand=True)
        self._current_view = view


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
