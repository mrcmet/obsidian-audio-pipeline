from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

PAD_INNER = 8
PAD_SECTION = 12
IS_WINDOWS = sys.platform == "win32"

TRANSCRIBER_BACKENDS = ["faster-whisper", "whisperx", "openai-api"]
LLM_BACKENDS = ["anthropic", "openai", "ollama"]
DEVICES = ["auto", "cpu", "cuda"]
COMPUTE_TYPES = ["float16", "int8", "float32"]
AUDIO_ACTIONS = ["archive", "delete", "leave"]


def _get_nested(data: dict, path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur if cur is not None else default


def _set_nested(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


class _SettingsWindow:
    def __init__(self, master: tk.Misc | None, config_path: str | None) -> None:
        self._owns_root = master is None
        if master is None:
            self.root: tk.Misc = tk.Tk()
        else:
            self.root = tk.Toplevel(master)

        self.root.title("Obsidian Audio Pipeline \u2014 Settings")
        self.root.geometry("720x620")

        if config_path is None:
            self.config_path = Path(__file__).resolve().parent / "config.yaml"
        else:
            self.config_path = Path(config_path)

        self.config_data: dict = self._load_config()
        self.vars: dict[str, Any] = {}

        self._build_ui()

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return {}
            return data
        except FileNotFoundError:
            messagebox.showwarning(
                "Config not found",
                f"Could not find {self.config_path}. Starting with empty config.",
            )
            return {}
        except yaml.YAMLError as exc:
            messagebox.showerror("YAML error", f"Could not parse config.yaml:\n{exc}")
            return {}

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=PAD_INNER)
        outer.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_folders_tab()
        self._build_transcription_tab()
        self._build_llm_tab()
        self._build_note_tab()

        button_row = ttk.Frame(outer, padding=(0, PAD_SECTION, 0, 0))
        button_row.pack(fill=tk.X)

        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(button_row, text="Save", command=self._save).pack(
            side=tk.RIGHT, padx=(0, PAD_INNER)
        )

    def _make_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.notebook, padding=PAD_SECTION)
        tab.columnconfigure(1, weight=1)
        return tab

    def _add_label(self, parent: ttk.Frame, row: int, text: str) -> None:
        ttk.Label(parent, text=text).grid(
            row=row, column=0, sticky=tk.W, padx=(0, PAD_INNER), pady=PAD_INNER
        )

    def _add_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        key: str,
        browse: str | None = None,
        hint: str | None = None,
    ) -> tk.StringVar:
        self._add_label(parent, row, label)
        var = tk.StringVar(value=str(_get_nested(self.config_data, key, "") or ""))
        self.vars[key] = var

        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=PAD_INNER)

        col = 2
        if browse and IS_WINDOWS:
            cmd = self._browse_dir(var) if browse == "dir" else self._browse_file(var)
            ttk.Button(parent, text="Browse...", command=cmd).grid(
                row=row, column=col, padx=(PAD_INNER, 0), pady=PAD_INNER
            )
            col += 1

        if hint:
            ttk.Label(parent, text=hint, foreground="#888").grid(
                row=row + 1, column=1, sticky=tk.W, pady=(0, PAD_INNER)
            )

        return var

    def _add_combobox(
        self, parent: ttk.Frame, row: int, label: str, key: str, values: list[str]
    ) -> tk.StringVar:
        self._add_label(parent, row, label)
        current = _get_nested(self.config_data, key, values[0])
        var = tk.StringVar(value=str(current) if current is not None else values[0])
        self.vars[key] = var
        combo = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky=tk.EW, pady=PAD_INNER)
        return var

    def _add_checkbox(
        self, parent: ttk.Frame, row: int, label: str, key: str
    ) -> tk.BooleanVar:
        self._add_label(parent, row, label)
        var = tk.BooleanVar(value=bool(_get_nested(self.config_data, key, False)))
        self.vars[key] = var
        ttk.Checkbutton(parent, variable=var).grid(
            row=row, column=1, sticky=tk.W, pady=PAD_INNER
        )
        return var

    def _browse_dir(self, var: tk.StringVar):
        def _cb() -> None:
            initial = os.path.expanduser(var.get()) if var.get() else ""
            path = filedialog.askdirectory(parent=self.root, initialdir=initial or None)
            if path:
                var.set(path)

        return _cb

    def _browse_file(self, var: tk.StringVar, filetypes=None):
        def _cb() -> None:
            initial = os.path.expanduser(var.get()) if var.get() else ""
            path = filedialog.askopenfilename(
                parent=self.root,
                initialdir=os.path.dirname(initial) if initial else None,
                filetypes=filetypes or [("All files", "*.*")],
            )
            if path:
                var.set(path)

        return _cb

    def _build_folders_tab(self) -> None:
        tab = self._make_tab()
        self.notebook.add(tab, text="Folders")

        self._add_entry(tab, 0, "Watch Folder", "watch_folder", browse="dir")
        self._add_entry(tab, 1, "Vault Inbox", "obsidian_vault_folder", browse="dir")
        self._add_entry(tab, 2, "Archive Folder", "archive_folder", browse="dir")
        self._add_combobox(
            tab, 3, "After Processing", "on_complete.audio_file_action", AUDIO_ACTIONS
        )

    def _build_transcription_tab(self) -> None:
        tab = self._make_tab()
        self.notebook.add(tab, text="Transcription")

        self._add_combobox(
            tab, 0, "Backend", "transcriber.backend", TRANSCRIBER_BACKENDS
        )
        self._add_entry(tab, 1, "Model", "transcriber.model")
        self._add_entry(
            tab,
            2,
            "Language",
            "transcriber.language",
            hint="ISO 639-1 code (e.g. en) or blank for auto",
        )
        self._add_combobox(tab, 4, "Device", "transcriber.device", DEVICES)
        self._add_combobox(
            tab, 5, "Compute Type", "transcriber.compute_type", COMPUTE_TYPES
        )
        self._add_entry(tab, 6, "Batch Size", "transcriber.batch_size")

        sep = ttk.Separator(tab, orient=tk.HORIZONTAL)
        sep.grid(row=7, column=0, columnspan=3, sticky=tk.EW, pady=PAD_SECTION)

        ttk.Label(tab, text="Diarization", font=("", 10, "bold")).grid(
            row=8, column=0, columnspan=3, sticky=tk.W, pady=(0, PAD_INNER)
        )

        self._add_checkbox(tab, 9, "Enabled", "transcriber.diarization.enabled")
        self._add_entry(
            tab, 10, "HF Token Env", "transcriber.diarization.hf_token_env"
        )

    def _build_llm_tab(self) -> None:
        tab = self._make_tab()
        self.notebook.add(tab, text="AI / LLM")

        self._add_combobox(tab, 0, "Backend", "llm.backend", LLM_BACKENDS)
        self._add_entry(tab, 1, "Model", "llm.model")
        self._add_entry(tab, 2, "API Key Env", "llm.api_key_env")

        ttk.Button(
            tab, text="Test Connection", command=self._test_connection
        ).grid(row=3, column=1, sticky=tk.W, pady=(PAD_SECTION, PAD_INNER))

    def _build_note_tab(self) -> None:
        tab = self._make_tab()
        self.notebook.add(tab, text="Note Format")

        self._add_label(tab, 0, "Template File")
        template_var = tk.StringVar(
            value=str(_get_nested(self.config_data, "note.template_file", "") or "")
        )
        self.vars["note.template_file"] = template_var
        ttk.Entry(tab, textvariable=template_var).grid(
            row=0, column=1, sticky=tk.EW, pady=PAD_INNER
        )
        if IS_WINDOWS:
            ttk.Button(
                tab,
                text="Browse...",
                command=self._browse_file(
                    template_var,
                    filetypes=[("Jinja2 templates", "*.j2"), ("All files", "*.*")],
                ),
            ).grid(row=0, column=2, padx=(PAD_INNER, 0), pady=PAD_INNER)

        self._add_checkbox(
            tab, 1, "Include Transcript", "note.include_full_transcript"
        )
        self._add_checkbox(tab, 2, "Collapse Transcript", "note.collapse_transcript")
        self._add_entry(
            tab,
            3,
            "Subfolder Pattern",
            "note.subfolder_pattern",
            hint="e.g. {year}/{month}",
        )

        self._add_label(tab, 5, "Custom Instructions")
        instructions_text = tk.Text(tab, height=4, wrap=tk.WORD)
        instructions_text.grid(
            row=5, column=1, columnspan=2, sticky=tk.EW, pady=PAD_INNER
        )
        existing_instructions = _get_nested(
            self.config_data, "note.custom_prompt_instructions", ""
        )
        instructions_text.insert("1.0", str(existing_instructions or ""))
        self.vars["note.custom_prompt_instructions"] = instructions_text

        self._add_label(tab, 6, "Fallback Tags")
        tags_text = tk.Text(tab, height=4, wrap=tk.WORD)
        tags_text.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=PAD_INNER)
        existing_tags = _get_nested(self.config_data, "note.fallback_tags", []) or []
        if isinstance(existing_tags, list):
            tags_text.insert("1.0", "\n".join(str(t) for t in existing_tags))
        self.vars["note.fallback_tags"] = tags_text

        ttk.Label(
            tab, text="One tag per line", foreground="#888"
        ).grid(row=7, column=1, sticky=tk.W, pady=(0, PAD_INNER))

    def _collect_values(self) -> dict:
        data = dict(self.config_data) if self.config_data else {}

        def deep_copy_dict(d: dict) -> dict:
            out: dict = {}
            for k, v in d.items():
                out[k] = deep_copy_dict(v) if isinstance(v, dict) else v
            return out

        data = deep_copy_dict(data)

        for key, widget in self.vars.items():
            if isinstance(widget, tk.BooleanVar):
                value: Any = widget.get()
            elif isinstance(widget, tk.StringVar):
                raw = widget.get().strip()
                if key == "transcriber.batch_size":
                    try:
                        value = int(raw) if raw else 0
                    except ValueError:
                        raise ValueError(f"Batch Size must be an integer, got: {raw!r}")
                elif key == "transcriber.language":
                    value = raw if raw else None
                else:
                    value = raw
            elif isinstance(widget, tk.Text):
                raw_text = widget.get("1.0", tk.END).rstrip("\n")
                if key == "note.fallback_tags":
                    value = [line.strip() for line in raw_text.splitlines() if line.strip()]
                else:
                    value = raw_text
            else:
                continue

            _set_nested(data, key, value)

        return data

    def _save(self) -> None:
        try:
            new_data = self._collect_values()
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self.root)
            return

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(new_data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
        except OSError as exc:
            messagebox.showerror(
                "Could not save",
                f"Failed to write {self.config_path}:\n{exc}",
                parent=self.root,
            )
            return

        messagebox.showinfo(
            "Saved",
            "Settings saved. Restart the pipeline for changes to take effect.",
            parent=self.root,
        )
        self._close()

    def _cancel(self) -> None:
        self._close()

    def _close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _test_connection(self) -> None:
        backend = self.vars["llm.backend"].get().strip()
        model = self.vars["llm.model"].get().strip()
        api_key_env = self.vars["llm.api_key_env"].get().strip()

        def worker() -> None:
            try:
                if backend == "anthropic":
                    import anthropic

                    key = os.environ.get(api_key_env, "")
                    anthropic.Anthropic(api_key=key).models.list()
                    msg = f"Connected to Anthropic (model: {model or 'n/a'})."
                elif backend == "openai":
                    import openai

                    key = os.environ.get(api_key_env, "")
                    openai.OpenAI(api_key=key).models.list()
                    msg = f"Connected to OpenAI (model: {model or 'n/a'})."
                elif backend == "ollama":
                    import urllib.request

                    urllib.request.urlopen(
                        "http://localhost:11434/api/tags", timeout=3
                    )
                    msg = "Connected to Ollama at localhost:11434."
                else:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "Unknown backend",
                            f"Unknown LLM backend: {backend!r}",
                            parent=self.root,
                        ),
                    )
                    return

                self.root.after(
                    0,
                    lambda m=msg: messagebox.showinfo(
                        "Connection OK", m, parent=self.root
                    ),
                )
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                self.root.after(
                    0,
                    lambda e=err: messagebox.showerror(
                        "Connection failed", e, parent=self.root
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> None:
        if self._owns_root:
            self.root.mainloop()


def open_settings_window(
    master: tk.Misc | None = None, config_path: str | None = None
) -> None:
    """Open the settings editor. config_path defaults to config.yaml next to this file."""
    window = _SettingsWindow(master, config_path)
    window.run()


if __name__ == "__main__":
    open_settings_window()
