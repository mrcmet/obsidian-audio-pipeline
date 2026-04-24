from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

LOG_FILENAME = "pipeline.log"
POLL_INTERVAL_MS = 500
BG = "#1e1e1e"
FG = "#d4d4d4"
DIM = "#6a6a6a"
FONT = ("Consolas", 10)


class _LogWindow:
    def __init__(self, master: tk.Misc | None = None) -> None:
        self._owns_root = master is None
        if master is None:
            self.root: tk.Misc = tk.Tk()
        else:
            self.root = tk.Toplevel(master)

        self.root.title("Obsidian Audio Pipeline \u2014 Log")
        self.root.geometry("900x600")
        self.root.configure(bg=BG)

        self.log_path = Path(__file__).resolve().parent / LOG_FILENAME
        self._file_pos = 0
        self._waiting_shown = False

        self._build_ui()
        self._poll()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=8)
        container.pack(fill=tk.BOTH, expand=True)

        text_frame = tk.Frame(container, bg=BG)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(
            text_frame,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            font=FONT,
            wrap=tk.NONE,
            borderwidth=0,
            highlightthickness=0,
            yscrollcommand=self.scrollbar.set,
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.text.yview)

        self.text.tag_configure("dim", foreground=DIM)
        self.text.configure(state=tk.DISABLED)

        button_row = ttk.Frame(container, padding=(0, 12, 0, 0))
        button_row.pack(fill=tk.X)

        ttk.Button(button_row, text="Clear", command=self._clear).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Close", command=self._close).pack(side=tk.RIGHT)

    def _is_at_bottom(self) -> bool:
        try:
            _, end = self.scrollbar.get()
        except tk.TclError:
            return True
        return end >= 0.999

    def _append(self, text: str, tag: str | None = None) -> None:
        at_bottom = self._is_at_bottom()
        self.text.configure(state=tk.NORMAL)
        if tag:
            self.text.insert(tk.END, text, tag)
        else:
            self.text.insert(tk.END, text)
        self.text.configure(state=tk.DISABLED)
        if at_bottom:
            self.text.see(tk.END)

    def _show_waiting(self) -> None:
        if self._waiting_shown:
            return
        self._waiting_shown = True
        self._append(f"Waiting for {LOG_FILENAME}...\n", "dim")

    def _clear_waiting(self) -> None:
        if not self._waiting_shown:
            return
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)
        self._waiting_shown = False

    def _clear(self) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)
        self._waiting_shown = False

    def _poll(self) -> None:
        try:
            if not self.log_path.exists():
                self._file_pos = 0
                self._show_waiting()
            else:
                try:
                    size = self.log_path.stat().st_size
                except OSError:
                    size = 0

                if size < self._file_pos:
                    self._file_pos = 0

                if size > self._file_pos:
                    try:
                        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self._file_pos)
                            new_data = f.read()
                            self._file_pos = f.tell()
                    except OSError:
                        new_data = ""

                    if new_data:
                        self._clear_waiting()
                        self._append(new_data)
        finally:
            self.root.after(POLL_INTERVAL_MS, self._poll)

    def _close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        if self._owns_root:
            self.root.mainloop()


def open_log_window(master: tk.Misc | None = None) -> None:
    """Open the log viewer. If master is None, creates a standalone Tk root."""
    window = _LogWindow(master)
    window.run()


if __name__ == "__main__":
    open_log_window()
