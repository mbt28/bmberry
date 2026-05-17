#!/usr/bin/env python3

import json
import os
import queue
import shlex
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import pygubu
except ImportError:
    pygubu = None


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
CONFIG_PATH = APP_DIR / "config.json"
UI_PATH = APP_DIR / "ui" / "cockpit.ui"
LOG_PATH_TEXT = "$HOME/.config/cockpit/ibus.log"
LOG_PATH = Path(os.path.expandvars(LOG_PATH_TEXT)).expanduser()
LOG_DIR = LOG_PATH.parent
BACKEND_BINARY = ROOT_DIR / "ibus_linux"

TRACE_PRESETS = {
    "None": "0",
    "Function": "1",
    "IBus": "2",
    "Input": "4",
    "State": "8",
    "Verbose": "15",
}

PRESET_COUNT = 5
NOTES_TEXT = (
    "This GUI only wraps the parent Linux bridge.\n"
    "Serial access and /dev/uinput permissions still\n"
    "need to be valid on this machine."
)


class CockpitApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Cockpit")
        self.root.geometry("1240x760")
        self.root.minsize(1060, 680)
        self.root.configure(bg="#eadfce")

        self.proc = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.reader_threads = []
        self.log_file_handle = None
        self.log_tail_thread = None
        self.log_tail_stop = threading.Event()
        self.radio_emulator = None

        self.device_var = tk.StringVar()
        self.hijack_var = tk.StringVar(value="AUX")
        self.video_var = tk.StringVar(value="CTS")
        self.trace_label_var = tk.StringVar(value="Verbose")
        self.trace_mask_var = tk.StringVar(value="15")
        self.log_var = tk.StringVar(value=LOG_PATH_TEXT)
        self.status_var = tk.StringVar(value="Idle")
        self.bridge_button_var = tk.StringVar(value="Start")
        self.backend_var = tk.StringVar(value=str(BACKEND_BINARY))
        self.tx_sender_var = tk.StringVar(value="68")
        self.tx_receiver_var = tk.StringVar(value="18")
        self.tx_message_var = tk.StringVar(value="38")
        self.tx_data_var = tk.StringVar(value="00 00")
        self.tx_frame_var = tk.StringVar(value="")
        self.tx_raw_var = tk.StringVar(value="")
        self.preset_buttons: list[ttk.Button] = []
        self.device_combos: list[ttk.Combobox] = []
        self.video_combos: list[ttk.Combobox] = []
        self.custom_presets = self._default_presets()

        self._load_config()
        self._build_ui()
        self._refresh_devices()
        self._pump_output()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self._configure_styles()
        if self._build_pygubu_ui():
            self._sync_hijack_ui()
            self._refresh_tx_preview()
            return
        self._build_builtin_ui()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Root.TFrame", background="#eadfce")
        style.configure("Panel.TFrame", background="#f7f1e6")
        style.configure("Card.TLabelframe", background="#f7f1e6", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background="#f7f1e6", foreground="#24313c")
        style.configure("Hero.TLabel", background="#eadfce", foreground="#1f2d36", font=("TkDefaultFont", 26, "bold"))
        style.configure("Meta.TLabel", background="#eadfce", foreground="#5a6770", font=("TkDefaultFont", 10))
        style.configure("Section.TLabel", background="#f7f1e6", foreground="#23303a", font=("TkDefaultFont", 11, "bold"))
        style.configure("Action.TButton", padding=(12, 8), font=("TkDefaultFont", 10, "bold"))
        style.configure("Quiet.TButton", padding=(10, 7))
        style.configure("Status.TLabel", background="#f7f1e6", foreground="#8b3d16", font=("TkDefaultFont", 11, "bold"))

    def _build_builtin_ui(self) -> None:
        outer = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="Root.TFrame")
        header.pack(fill="x")

        ttk.Label(header, text="Cockpit", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Linux GUI frontend for the parent BMW I-Bus bridge",
            style="Meta.TLabel",
        ).pack(anchor="w", pady=(2, 16))

        body = ttk.Frame(outer, style="Root.TFrame")
        body.pack(fill="both", expand=True)

        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        console_wrap = ttk.Frame(body, style="Panel.TFrame", padding=0)
        console_wrap.grid(row=0, column=0, sticky="nsew")
        console_wrap.rowconfigure(1, weight=1)
        console_wrap.columnconfigure(0, weight=1)

        self._build_console(console_wrap)
        self._sync_hijack_ui()
        self._refresh_tx_preview()

    def _build_pygubu_ui(self) -> bool:
        if pygubu is None or not UI_PATH.exists():
            return False

        try:
            builder = pygubu.Builder()
            builder.add_from_file(UI_PATH)
            self._seed_pygubu_variables(builder)
            builder.get_object("main_frame", self.root)
            builder.import_widgets(self, user_named=True)
            self.ui_builder = builder
            self._wire_pygubu_widgets()
        except Exception as exc:
            print(f"Unable to load Pygubu UI from {UI_PATH}: {exc}")
            for child in self.root.winfo_children():
                child.destroy()
            return False
        return True

    def _seed_pygubu_variables(self, builder) -> None:
        builder.tkvariables.update({
            "device_var": self.device_var,
            "hijack_var": self.hijack_var,
            "video_var": self.video_var,
            "trace_label_var": self.trace_label_var,
            "trace_mask_var": self.trace_mask_var,
            "log_var": self.log_var,
            "status_var": self.status_var,
            "bridge_button_var": self.bridge_button_var,
            "backend_var": self.backend_var,
            "tx_sender_var": self.tx_sender_var,
            "tx_receiver_var": self.tx_receiver_var,
            "tx_message_var": self.tx_message_var,
            "tx_data_var": self.tx_data_var,
            "tx_frame_var": self.tx_frame_var,
            "tx_raw_var": self.tx_raw_var,
        })

    def _wire_pygubu_widgets(self) -> None:
        self.bridge_button.configure(command=self._toggle_backend)
        self.radio_button.configure(command=self._open_radio_popup)
        if hasattr(self, "settings_button"):
            self.settings_button.configure(command=self._open_settings)
        if hasattr(self, "about_button"):
            self.about_button.configure(command=self._open_about)
        self.clear_console_button.configure(command=self._clear_console)
        self.copy_message_button.configure(command=self._copy_selected_message)
        self.send_raw_button.configure(command=self._send_raw_ibus_message)
        self.preset_settings_button.configure(command=self._open_preset_settings)
        self.build_into_raw_button.configure(command=self._fill_raw_from_preview)
        self.send_built_button.configure(command=self._send_ibus_message)
        self.tx_frame_entry.configure(state="readonly")

        self.tx_raw_entry.bind("<KeyRelease>", lambda _event: self._normalize_raw_preview())
        for entry in (self.tx_sender_entry, self.tx_receiver_entry, self.tx_message_entry, self.tx_data_entry):
            entry.bind("<KeyRelease>", lambda _event: self._refresh_tx_preview())

        self.preset_buttons = [
            self.preset_button_1,
            self.preset_button_2,
            self.preset_button_3,
            self.preset_button_4,
            self.preset_button_5,
        ]
        for idx, button in enumerate(self.preset_buttons):
            button.configure(command=lambda index=idx: self._send_preset(index))

        self._build_console_table(self.console_table_frame)
        self._append_console("Cockpit ready.\n", "meta")
        self._refresh_preset_buttons()

    def _register_device_combo(self, combo: ttk.Combobox) -> None:
        self.device_combos = [widget for widget in self.device_combos if widget.winfo_exists()]
        if combo not in self.device_combos:
            self.device_combos.append(combo)

    def _register_video_combo(self, combo: ttk.Combobox) -> None:
        self.video_combos = [widget for widget in self.video_combos if widget.winfo_exists()]
        if combo not in self.video_combos:
            self.video_combos.append(combo)

    def _build_console_table(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.console = ttk.Treeview(
            parent,
            columns=("time", "sender", "receiver", "message", "description"),
            show="headings",
            height=18,
        )
        self.console.grid(row=0, column=0, sticky="nsew")
        self.console.heading("time", text="Time")
        self.console.heading("sender", text="Sender")
        self.console.heading("receiver", text="Receiver")
        self.console.heading("message", text="Message")
        self.console.heading("description", text="Description")
        self.console.column("time", width=90, minwidth=85, stretch=False, anchor="w")
        self.console.column("sender", width=190, minwidth=150, stretch=False, anchor="w")
        self.console.column("receiver", width=190, minwidth=150, stretch=False, anchor="w")
        self.console.column("message", width=260, minwidth=220, stretch=True, anchor="w")
        self.console.column("description", width=360, minwidth=280, stretch=True, anchor="w")
        self.console.tag_configure("error", foreground="#b42318")
        self.console.tag_configure("meta", foreground="#175cd3")
        self.console.tag_configure("ok", foreground="#027a48")
        self.console.bind("<Double-1>", lambda _event: self._copy_selected_message())

        y_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.console.yview)
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=self.console.xview)
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.console.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)

    def _build_console(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        actions = ttk.Frame(top, style="Panel.TFrame")
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        actions.columnconfigure((0, 1, 2, 3, 4), weight=1)
        ttk.Button(actions, textvariable=self.bridge_button_var, style="Action.TButton", command=self._toggle_backend).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="RADIO", style="Quiet.TButton", command=self._open_radio_popup).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Settings", style="Quiet.TButton", command=self._open_settings).grid(row=0, column=2, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="About", style="Quiet.TButton", command=self._open_about).grid(row=0, column=3, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Clear Console", style="Quiet.TButton", command=self._clear_console).grid(row=0, column=4, sticky="ew")

        ttk.Label(top, text="Live Console", style="Section.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Button(top, text="📋 Copy Message", style="Quiet.TButton", command=self._copy_selected_message).grid(row=1, column=1, sticky="e", padx=(0, 8))

        table_frame = ttk.Frame(parent, style="Panel.TFrame", padding=(16, 0, 16, 16))
        table_frame.grid(row=1, column=0, sticky="nsew")
        self._build_console_table(table_frame)

        self._append_console("Cockpit ready.\n", "meta")

        composer = ttk.LabelFrame(parent, text="IBus Composer", style="Card.TLabelframe", padding=16)
        composer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        composer.columnconfigure(0, weight=1)

        ttk.Label(composer, text="Raw frame", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        raw_row = ttk.Frame(composer, style="Panel.TFrame")
        raw_row.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        raw_row.columnconfigure(0, weight=1)
        raw_entry = ttk.Entry(raw_row, textvariable=self.tx_raw_var)
        raw_entry.grid(row=0, column=0, sticky="ew")
        raw_entry.bind("<KeyRelease>", lambda _event: self._normalize_raw_preview())
        ttk.Button(raw_row, text="Send Raw Frame", style="Action.TButton", command=self._send_raw_ibus_message).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(raw_row, text="Preset Settings", style="Quiet.TButton", command=self._open_preset_settings).grid(row=0, column=2, padx=(8, 0))

        preset_row = ttk.Frame(composer, style="Panel.TFrame")
        preset_row.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for idx in range(PRESET_COUNT):
            preset_row.columnconfigure(idx, weight=1)
            button = ttk.Button(
                preset_row,
                text=f"Preset {idx + 1}",
                style="Quiet.TButton",
                command=lambda index=idx: self._send_preset(index),
            )
            button.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 8, 0))
            self.preset_buttons.append(button)

        helper = ttk.Frame(composer, style="Panel.TFrame")
        helper.grid(row=3, column=0, sticky="ew")
        for idx in range(4):
            helper.columnconfigure(idx, weight=1)

        self._tx_inline_field(helper, "Sender", self.tx_sender_var, 0)
        self._tx_inline_field(helper, "Receiver", self.tx_receiver_var, 1)
        self._tx_inline_field(helper, "Message", self.tx_message_var, 2)
        self._tx_inline_field(helper, "Data bytes", self.tx_data_var, 3)

        preview_row = ttk.Frame(composer, style="Panel.TFrame")
        preview_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        preview_row.columnconfigure(0, weight=1)
        ttk.Label(preview_row, text="Built frame", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(preview_row, textvariable=self.tx_frame_var, state="readonly").grid(row=1, column=0, sticky="ew", pady=(4, 0))
        actions = ttk.Frame(preview_row, style="Panel.TFrame")
        actions.grid(row=1, column=1, padx=(8, 0), sticky="e")
        ttk.Button(actions, text="Build Into Raw", style="Quiet.TButton", command=self._fill_raw_from_preview).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(actions, text="Send Built Frame", style="Quiet.TButton", command=self._send_ibus_message).grid(row=0, column=1)
        self._refresh_preset_buttons()

    def _labeled_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, browse_backend: bool = False) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text=label, style="Section.TLabel").pack(anchor="w")

        row = ttk.Frame(wrap, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=variable).grid(row=0, column=0, sticky="ew")

        if browse_backend:
            ttk.Button(row, text="Browse", style="Quiet.TButton", command=self._browse_backend).grid(row=0, column=1, padx=(8, 0))

    def _device_row(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text="Serial device", style="Section.TLabel").pack(anchor="w")

        row = ttk.Frame(wrap, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(0, weight=1)

        self.device_combo = ttk.Combobox(row, textvariable=self.device_var)
        self.device_combo.grid(row=0, column=0, sticky="ew")
        self._register_device_combo(self.device_combo)
        ttk.Button(row, text="Refresh", style="Quiet.TButton", command=self._refresh_devices).grid(row=0, column=1, padx=(8, 0))

    def _combo_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str]) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text=label, style="Section.TLabel").pack(anchor="w")
        combo = ttk.Combobox(wrap, textvariable=variable, values=values, state="readonly")
        combo.pack(fill="x", pady=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())

    def _hijack_row(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text="Hijack state", style="Section.TLabel").pack(anchor="w")
        self.hijack_combo = ttk.Combobox(
            wrap,
            textvariable=self.hijack_var,
            values=["NONE", "AUX", "TAPE", "FM"],
            state="readonly",
        )
        self.hijack_combo.pack(fill="x", pady=(4, 0))
        self.hijack_combo.bind("<<ComboboxSelected>>", self._on_hijack_selected)

    def _video_row(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text="Video switch", style="Section.TLabel").pack(anchor="w")
        self.video_combo = ttk.Combobox(
            wrap,
            textvariable=self.video_var,
            values=["CTS", "RTS", "GPIO"],
            state="readonly",
        )
        self.video_combo.pack(fill="x", pady=(4, 0))
        self._register_video_combo(self.video_combo)
        self.video_combo.bind("<<ComboboxSelected>>", lambda _event: self._save_config())

    def _trace_row(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x", pady=(0, 10))
        ttk.Label(wrap, text="Trace preset", style="Section.TLabel").pack(anchor="w")

        row = ttk.Frame(wrap, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=0)

        trace_combo = ttk.Combobox(
            row,
            textvariable=self.trace_label_var,
            values=list(TRACE_PRESETS.keys()),
            state="readonly",
        )
        trace_combo.grid(row=0, column=0, sticky="ew")
        trace_combo.bind("<<ComboboxSelected>>", self._on_trace_selected)
        ttk.Entry(row, textvariable=self.trace_mask_var, width=8).grid(row=0, column=1, padx=(8, 0))

    def _log_row(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="x")
        ttk.Label(wrap, text="Log file", style="Section.TLabel").pack(anchor="w")

        row = ttk.Frame(wrap, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self.log_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="Choose", style="Quiet.TButton", command=self._choose_log_path).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(row, text="Default", style="Quiet.TButton", command=self._use_default_log_path).grid(row=0, column=2, padx=(8, 0))

    def _append_console(self, text: str, tag: str = "info") -> None:
        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue
            timestamp, sender, receiver, message, description = self._parse_console_line(raw_line)
            if self.radio_emulator is not None and message:
                self.radio_emulator.consume_frame(message, sender, receiver, description)
            self.console.insert("", "end", values=(timestamp, sender, receiver, message, description), tags=(tag,))
        children = self.console.get_children()
        if children:
            self.console.see(children[-1])

    def _format_log_time(self, value: str) -> str:
        try:
            return time.strftime("%H:%M:%S", time.localtime(float(value)))
        except (ValueError, OverflowError):
            return value

    def _parse_console_line(self, line: str) -> tuple[str, str, str, str, str]:
        cleaned = line.strip()
        if cleaned.startswith("$ "):
            return "", "", "", cleaned[2:], "Command"

        timestamp = ""
        payload = cleaned
        if ": " in cleaned:
            prefix, rest = cleaned.split(": ", 1)
            if prefix.replace(".", "", 1).isdigit():
                timestamp = self._format_log_time(prefix)
                payload = rest.strip()

        if " = " in payload:
            message, description = payload.split(" = ", 1)
            sender = ""
            receiver = ""
            if " SENT " in description and " TO " in description:
                sender, remainder = description.split(" SENT ", 1)
                _action, receiver_part = remainder.rsplit(" TO ", 1)
                receiver = receiver_part.split(" DATA:", 1)[0].strip()
            return timestamp, sender.strip(), receiver.strip(), message.strip(), description.strip()

        if cleaned.startswith("Sent IBus frame:"):
            return timestamp, "", "", cleaned.split(":", 1)[1].strip(), "Sent IBus frame"

        if cleaned.startswith("Process exited with code"):
            return timestamp, "", "", "", cleaned

        if cleaned.startswith("Stopping backend"):
            return timestamp, "", "", "", cleaned

        return timestamp, "", "", "", payload

    def _tx_inline_field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, column: int) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(wrap, text=label, style="Section.TLabel").pack(anchor="w")
        entry = ttk.Entry(wrap, textvariable=variable)
        entry.pack(fill="x", pady=(4, 0))
        entry.bind("<KeyRelease>", lambda _event: self._refresh_tx_preview())

    def _clear_console(self) -> None:
        self.console.delete(*self.console.get_children())
        self._append_console("Console cleared.\n", "meta")

    def _copy_selected_message(self) -> None:
        selection = self.console.selection()
        if not selection:
            self._set_status("No row selected")
            return

        values = self.console.item(selection[0], "values")
        if len(values) < 4 or not values[3]:
            self._set_status("Selected row has no message")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(values[3])
        self._set_status("Message copied")

    def _open_radio_popup(self) -> None:
        if self.radio_emulator is None:
            from emulators.radio import RadioEmulator
            self.radio_emulator = RadioEmulator(self.root)
        self.radio_emulator.show(self.tx_raw_var.get().strip())
        for row_id in self.console.get_children():
            values = self.console.item(row_id, "values")
            if len(values) >= 5 and values[3]:
                self.radio_emulator.consume_frame(values[3], values[1], values[2], values[4])

    def _refresh_devices(self) -> None:
        patterns = [
            "/dev/ttyUSB*",
            "/dev/ttyACM*",
            "/dev/ttyS*",
            "/dev/ttyAMA*",
            "/dev/rfcomm*",
        ]
        devices = []
        for pattern in patterns:
            devices.extend(sorted(str(path) for path in Path("/").glob(pattern[1:])))

        self.device_combos = [combo for combo in self.device_combos if combo.winfo_exists()]
        for combo in self.device_combos:
            combo["values"] = devices
        if not self.device_var.get() and devices:
            self.device_var.set(devices[0])
        self._save_config()

    def _browse_backend(self) -> None:
        selected = filedialog.askopenfilename(initialdir=str(ROOT_DIR), title="Select backend binary")
        if selected:
            self.backend_var.set(selected)
            self._save_config()

    def _choose_log_path(self) -> None:
        current = Path(os.path.expandvars(self.log_var.get())).expanduser()
        initialdir = current.parent if str(current.parent) != "." else LOG_DIR
        initialdir.mkdir(parents=True, exist_ok=True)
        selected = filedialog.asksaveasfilename(
            initialdir=str(initialdir),
            initialfile=current.name or LOG_PATH.name,
            title="Select log file",
        )
        if selected:
            self.log_var.set(selected)
            self._save_config()

    def _use_default_log_path(self) -> None:
        self.log_var.set(LOG_PATH_TEXT)
        self._save_config()

    def _on_trace_selected(self, _event=None) -> None:
        self.trace_mask_var.set(TRACE_PRESETS.get(self.trace_label_var.get(), self.trace_mask_var.get()))
        self._save_config()

    def _on_hijack_selected(self, _event=None) -> None:
        self._sync_hijack_ui()
        self._save_config()

    def _sync_hijack_ui(self) -> None:
        self.video_combos = [combo for combo in self.video_combos if combo.winfo_exists()]
        if self.hijack_var.get().strip().upper() == "NONE":
            for combo in self.video_combos:
                combo.configure(state="disabled")
        else:
            for combo in self.video_combos:
                combo.configure(state="readonly")

    def _default_presets(self) -> list[dict[str, str]]:
        return [
            {"label": f"Preset {index + 1}", "frame": ""}
            for index in range(PRESET_COUNT)
        ]

    def _refresh_preset_buttons(self) -> None:
        for index, button in enumerate(self.preset_buttons):
            preset = self.custom_presets[index]
            button.configure(text=preset.get("label", f"Preset {index + 1}"))

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#eadfce")

        frame = ttk.Frame(dialog, style="Root.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(frame, text="Bridge Settings", style="Card.TLabelframe", padding=12)
        settings.pack(fill="both", expand=True)

        self._labeled_entry(settings, "Backend binary", self.backend_var, browse_backend=True)
        self._device_row(settings)
        self._hijack_row(settings)
        self._video_row(settings)
        self._trace_row(settings)
        self._log_row(settings)

        ttk.Label(
            settings,
            text=f"Default log: {LOG_PATH_TEXT}",
            background="#f7f1e6",
            foreground="#4e5a61",
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.Frame(frame, style="Root.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        actions.columnconfigure((0, 1), weight=1)

        def save_and_close() -> None:
            self._save_config()
            dialog.destroy()

        ttk.Button(actions, text="Save", style="Action.TButton", command=save_and_close).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Close", style="Quiet.TButton", command=save_and_close).grid(row=0, column=1, sticky="ew")
        dialog.protocol("WM_DELETE_WINDOW", save_and_close)

        self._refresh_devices()
        self._sync_hijack_ui()

    def _open_about(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("About Cockpit")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#eadfce")

        frame = ttk.Frame(dialog, style="Root.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        notes = ttk.LabelFrame(frame, text="Notes", style="Card.TLabelframe", padding=12)
        notes.pack(fill="both", expand=True)
        ttk.Label(
            notes,
            text=NOTES_TEXT,
            background="#f7f1e6",
            foreground="#4e5a61",
            justify="left",
        ).pack(anchor="w")

        ttk.Button(frame, text="Close", style="Action.TButton", command=dialog.destroy).pack(fill="x", pady=(12, 0))

    def _open_preset_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Preset Settings")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#eadfce")

        frame = ttk.Frame(dialog, style="Root.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        editors: list[tuple[tk.StringVar, tk.StringVar]] = []
        for index, preset in enumerate(self.custom_presets):
            card = ttk.LabelFrame(frame, text=f"Button {index + 1}", style="Card.TLabelframe", padding=12)
            card.pack(fill="x", pady=(0, 10))

            label_var = tk.StringVar(value=preset.get("label", f"Preset {index + 1}"))
            frame_var = tk.StringVar(value=preset.get("frame", ""))
            editors.append((label_var, frame_var))

            ttk.Label(card, text="Name", style="Section.TLabel").pack(anchor="w")
            ttk.Entry(card, textvariable=label_var).pack(fill="x", pady=(4, 8))
            ttk.Label(card, text="Raw frame", style="Section.TLabel").pack(anchor="w")
            ttk.Entry(card, textvariable=frame_var).pack(fill="x", pady=(4, 0))

        actions = ttk.Frame(frame, style="Root.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        actions.columnconfigure((0, 1), weight=1)

        def save_and_close() -> None:
            updated: list[dict[str, str]] = []
            for index, (label_var, frame_var) in enumerate(editors):
                label = label_var.get().strip() or f"Preset {index + 1}"
                frame_text = frame_var.get().strip().upper()
                if frame_text:
                    try:
                        self._parse_hex_sequence(frame_text)
                    except ValueError as exc:
                        messagebox.showerror("Invalid preset", f"{label}: {exc}", parent=dialog)
                        return
                updated.append({"label": label, "frame": frame_text})

            self.custom_presets = updated
            self._refresh_preset_buttons()
            self._save_config()
            dialog.destroy()

        ttk.Button(actions, text="Save", style="Action.TButton", command=save_and_close).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).grid(row=0, column=1, sticky="ew")

    def _send_preset(self, index: int) -> None:
        preset = self.custom_presets[index]
        frame_text = preset.get("frame", "").strip()
        if not frame_text:
            self._set_status("Preset has no message")
            return
        self.tx_raw_var.set(frame_text)
        self._save_config()
        self._send_raw_ibus_message()

    def _save_config(self) -> None:
        payload = {
            "device": self.device_var.get(),
            "hijack_state": self.hijack_var.get(),
            "video_switch": self.video_var.get(),
            "trace_label": self.trace_label_var.get(),
            "trace_mask": self.trace_mask_var.get(),
            "log_file": self.log_var.get(),
            "backend_binary": self.backend_var.get(),
            "tx_sender": self.tx_sender_var.get(),
            "tx_receiver": self.tx_receiver_var.get(),
            "tx_message": self.tx_message_var.get(),
            "tx_data": self.tx_data_var.get(),
            "tx_raw": self.tx_raw_var.get(),
            "custom_presets": self.custom_presets,
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _migrate_log_path(self, value: str) -> str:
        text = str(value).strip()
        if not text:
            return LOG_PATH_TEXT

        return text

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.device_var.set(data.get("device", self.device_var.get()))
        self.hijack_var.set(data.get("hijack_state", self.hijack_var.get()))
        self.video_var.set(data.get("video_switch", self.video_var.get()))
        self.trace_label_var.set(data.get("trace_label", self.trace_label_var.get()))
        self.trace_mask_var.set(data.get("trace_mask", self.trace_mask_var.get()))
        self.log_var.set(self._migrate_log_path(data.get("log_file", self.log_var.get())))
        self.backend_var.set(data.get("backend_binary", self.backend_var.get()))
        self.tx_sender_var.set(data.get("tx_sender", self.tx_sender_var.get()))
        self.tx_receiver_var.set(data.get("tx_receiver", self.tx_receiver_var.get()))
        self.tx_message_var.set(data.get("tx_message", self.tx_message_var.get()))
        self.tx_data_var.set(data.get("tx_data", self.tx_data_var.get()))
        self.tx_raw_var.set(data.get("tx_raw", self.tx_raw_var.get()))
        presets = data.get("custom_presets")
        if isinstance(presets, list) and len(presets) == PRESET_COUNT:
            normalized: list[dict[str, str]] = []
            for index, preset in enumerate(presets):
                if isinstance(preset, dict):
                    normalized.append({
                        "label": str(preset.get("label", f"Preset {index + 1}")),
                        "frame": str(preset.get("frame", "")).strip().upper(),
                    })
                else:
                    normalized.append({"label": f"Preset {index + 1}", "frame": ""})
            self.custom_presets = normalized

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        if text == "Running":
            self.bridge_button_var.set("Stop")
        else:
            self.bridge_button_var.set("Start")

    def _toggle_backend(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._stop_backend()
        else:
            self._start_backend()

    def _enqueue_line(self, line: str, tag: str = "info") -> None:
        self.output_queue.put((line, tag))

    def _pump_output(self) -> None:
        try:
            while True:
                line, tag = self.output_queue.get_nowait()
                self._append_console(line, tag)
        except queue.Empty:
            pass
        self.root.after(120, self._pump_output)

    def _build_command(self) -> list[str]:
        backend = self.backend_var.get().strip()
        if not backend:
            raise ValueError("Backend binary path is empty.")
        backend = str(Path(os.path.expandvars(backend)).expanduser())

        device = self.device_var.get().strip()
        if not device:
            raise ValueError("Serial device is required.")

        cmd = [
            backend,
            "-d",
            device,
            "-h",
            self.hijack_var.get().strip().upper() or "NONE",
            "-t",
            self.trace_mask_var.get().strip() or "15",
            "-f",
            str(Path(os.path.expandvars(self.log_var.get().strip() or LOG_PATH_TEXT)).expanduser()),
        ]
        if self.hijack_var.get().strip().upper() != "NONE":
            cmd.extend(["-v", self.video_var.get().strip() or "CTS"])
        return cmd

    def _parse_hex_byte(self, value: str, field: str) -> int:
        text = value.strip().lower().removeprefix("0x")
        if not text:
            raise ValueError(f"{field} is required.")
        if len(text) > 2:
            raise ValueError(f"{field} must be one byte.")
        try:
            parsed = int(text, 16)
        except ValueError as exc:
            raise ValueError(f"{field} must be valid hex.") from exc
        if not 0 <= parsed <= 0xFF:
            raise ValueError(f"{field} must be between 00 and FF.")
        return parsed

    def _parse_hex_data(self, value: str) -> list[int]:
        text = value.strip()
        if not text:
            return []
        parts = text.replace(",", " ").split()
        return [self._parse_hex_byte(part, "Data byte") for part in parts]

    def _parse_hex_sequence(self, value: str) -> list[int]:
        text = value.strip()
        if not text:
            raise ValueError("Raw frame is required.")
        parts = text.replace(",", " ").split()
        return [self._parse_hex_byte(part, "Raw frame byte") for part in parts]

    def _build_ibus_frame(self) -> list[int]:
        sender = self._parse_hex_byte(self.tx_sender_var.get(), "Sender")
        receiver = self._parse_hex_byte(self.tx_receiver_var.get(), "Receiver")
        message = self._parse_hex_byte(self.tx_message_var.get(), "Message")
        data = self._parse_hex_data(self.tx_data_var.get())

        length = 3 + len(data)
        frame = [sender, length, receiver, message, *data]
        checksum = 0
        for byte in frame:
            checksum ^= byte
        frame.append(checksum)
        return frame

    def _refresh_tx_preview(self) -> None:
        try:
            frame = self._build_ibus_frame()
            self.tx_frame_var.set(" ".join(f"{byte:02X}" for byte in frame))
        except ValueError:
            self.tx_frame_var.set("Invalid frame")

    def _normalize_raw_preview(self) -> None:
        self._save_config()

    def _fill_raw_from_preview(self) -> None:
        self._refresh_tx_preview()
        if self.tx_frame_var.get() != "Invalid frame":
            self.tx_raw_var.set(self.tx_frame_var.get())
            self._save_config()

    def _send_ibus_message(self) -> None:
        try:
            frame = self._build_ibus_frame()
        except ValueError as exc:
            messagebox.showerror("Invalid message", str(exc))
            return
        self.tx_raw_var.set(" ".join(f"{byte:02X}" for byte in frame))
        self._save_config()
        self._send_frame_bytes(frame)

    def _send_raw_ibus_message(self) -> None:
        try:
            frame = self._parse_hex_sequence(self.tx_raw_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid message", str(exc))
            return
        self._send_frame_bytes(frame)

    def _send_frame_bytes(self, frame: list[int]) -> None:
        try:
            device = self.device_var.get().strip()
            if not device:
                raise ValueError("Serial device is required.")
            self._save_config()
        except ValueError as exc:
            messagebox.showerror("Send failed", str(exc))
            return

        frame_hex = "".join(f"{byte:02x}" for byte in frame)
        helper = (
            "import os,sys,termios;"
            "dev=sys.argv[1];"
            "data=bytes.fromhex(sys.argv[2]);"
            "fd=os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_SYNC);"
            "attrs=termios.tcgetattr(fd);"
            "attrs[0]=termios.IGNPAR | termios.IGNBRK;"
            "attrs[1]=0;"
            "attrs[2]=termios.B9600 | termios.CS8 | termios.PARENB | termios.CLOCAL | termios.CREAD;"
            "attrs[3]=0;"
            "attrs[6][termios.VMIN]=1;"
            "attrs[6][termios.VTIME]=0;"
            "termios.tcflush(fd, termios.TCIFLUSH);"
            "termios.tcsetattr(fd, termios.TCSANOW, attrs);"
            "os.write(fd, data);"
            "termios.tcdrain(fd);"
            "os.close(fd)"
        )
        launch_cmd = ["python3", "-c", helper, device, frame_hex]

        self._enqueue_line(f"$ {' '.join(shlex.quote(part) for part in launch_cmd)}\n", "meta")

        try:
            result = subprocess.run(
                launch_cmd,
                text=True,
                capture_output=True,
                cwd=str(APP_DIR),
                check=False,
            )
        except Exception as exc:
            messagebox.showerror("Send failed", str(exc))
            self._set_status("Send failed")
            return

        if result.stdout:
            self._enqueue_line(result.stdout, "info")
        if result.stderr:
            self._enqueue_line(result.stderr, "error")

        if result.returncode == 0:
            self._enqueue_line(f"Sent IBus frame: {' '.join(f'{byte:02X}' for byte in frame)}\n", "ok")
            self._set_status("Message sent")
        else:
            self._enqueue_line(f"IBus send failed with code {result.returncode}.\n", "error")
            self._set_status("Send failed")

    def _start_backend(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Already running", "The backend is already running.")
            return

        self._save_config()
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            launch_cmd = self._build_command()
        except ValueError as exc:
            messagebox.showerror("Invalid configuration", str(exc))
            return

        if not Path(launch_cmd[0]).exists():
            messagebox.showerror("Missing backend", f"Backend binary not found:\n{launch_cmd[0]}")
            return

        try:
            log_path = Path(os.path.expandvars(self.log_var.get())).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file_handle = open(log_path, "a", encoding="utf-8")
            self.log_tail_stop.clear()

            self._enqueue_line(f"$ {' '.join(launch_cmd)}\n", "meta")
            self.proc = subprocess.Popen(
                launch_cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._set_status("Running")

            self.reader_threads = [
                threading.Thread(target=self._stream_reader, args=(self.proc.stdout, "info"), daemon=True),
                threading.Thread(target=self._stream_reader, args=(self.proc.stderr, "error"), daemon=True),
                threading.Thread(target=self._watch_process, daemon=True),
            ]
            self.log_tail_thread = threading.Thread(
                target=self._tail_log_file,
                args=(log_path,),
                daemon=True,
            )
            for thread in self.reader_threads:
                thread.start()
            self.log_tail_thread.start()
        except Exception as exc:
            if self.log_file_handle:
                self.log_file_handle.close()
                self.log_file_handle = None
            messagebox.showerror("Launch failed", str(exc))
            self._set_status("Launch failed")

    def _stream_reader(self, pipe, tag: str) -> None:
        try:
            for line in iter(pipe.readline, ""):
                self._enqueue_line(line, tag)
                if self.log_file_handle:
                    self.log_file_handle.write(line)
                    self.log_file_handle.flush()
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _watch_process(self) -> None:
        if not self.proc:
            return
        code = self.proc.wait()
        time.sleep(0.1)
        self.log_tail_stop.set()
        if self.log_file_handle:
            self.log_file_handle.flush()
            self.log_file_handle.close()
            self.log_file_handle = None
        self._enqueue_line(f"Process exited with code {code}.\n", "meta" if code == 0 else "error")
        self.root.after(0, lambda: self._set_status("Exited" if code == 0 else "Stopped with error"))
        self.proc = None

    def _tail_log_file(self, path: Path) -> None:
        waited = 0.0
        while not path.exists() and not self.log_tail_stop.is_set() and waited < 5.0:
            time.sleep(0.1)
            waited += 0.1
        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(0, os.SEEK_END)
                while not self.log_tail_stop.is_set():
                    line = handle.readline()
                    if line:
                        self._enqueue_line(line, "info")
                    else:
                        time.sleep(0.12)
        except Exception as exc:
            self._enqueue_line(f"Log tail error: {exc}\n", "error")

    def _stop_backend(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            self._set_status("Idle")
            return
        self._enqueue_line("Stopping backend...\n", "meta")
        self.log_tail_stop.set()
        self.proc.terminate()

    def _on_close(self) -> None:
        self._save_config()
        if self.proc and self.proc.poll() is None:
            self.log_tail_stop.set()
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = CockpitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
