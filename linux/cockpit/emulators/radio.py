#!/usr/bin/env python3

import time
from pathlib import Path
import tkinter as tk

try:
    import pygubu
except ImportError:
    pygubu = None


WIDTH = 400
HEIGHT = 234
UI_PATH = Path(__file__).resolve().parent.parent / "ui" / "radio.ui"

SRC_SERVICE = 0x00
SRC_WEATHER = 0x20
SRC_ANALOGUE = 0x40
SRC_DIGITAL = 0x60
SRC_TAPE = 0x80
SRC_TRAFFIC = 0xA0
SRC_CDC = 0xC0

SOURCE_META = {
    SRC_SERVICE: ("service", "SER"),
    SRC_WEATHER: ("weather", "WB"),
    SRC_ANALOGUE: ("analogue", "FMA"),
    SRC_DIGITAL: ("digital", "FMD"),
    SRC_TAPE: ("tape", "TAPE"),
    SRC_TRAFFIC: ("traffic", "TP"),
    SRC_CDC: ("cdc", "CDC"),
}

ANALOGUE_SELECT = [
    ("m", "Manual station tune"),
    ("SCAN", "Station sample"),
    ("II", "Search sensitive"),
    ("I", "Search non sensitive"),
]
CDC_SELECT = [
    ("<< >>", "Fast forward/reverse"),
    ("SCAN", "Track sample"),
    ("RANDOM", "Random generator"),
    ("< >", "Music search"),
]
TAPE_SELECT = [
    ("< >", "Music search"),
    ("<< >>", "Fast forward/reverse"),
]
TONE_ROWS = ["Bass", "Treble", "Fader", "Balance"]

BALANCE_VALUES = {
    0x0F: 10, 0x0E: 9, 0x0C: 8, 0x0A: 7, 0x08: 6, 0x05: 5, 0x04: 4, 0x03: 3, 0x02: 2, 0x01: 1,
    0x00: 0,
    0x11: -1, 0x12: -2, 0x13: -3, 0x14: -4, 0x15: -5, 0x18: -6, 0x1A: -7, 0x1C: -8, 0x1E: -9, 0x1F: -10,
}
FADER_VALUES = {
    0x1F: -10, 0x1E: -9, 0x1C: -8, 0x1A: -7, 0x18: -6, 0x15: -5, 0x14: -4, 0x13: -3, 0x12: -2, 0x11: -1,
    0x10: 0,
    0x01: 1, 0x02: 2, 0x03: 3, 0x04: 4, 0x05: 5, 0x08: 6, 0x0A: 7, 0x0C: 8, 0x0E: 9, 0x0F: 10,
}
TONE_VALUES = {
    0x1C: -6, 0x1A: -5, 0x18: -4, 0x16: -3, 0x14: -2, 0x12: -1,
    0x10: 0,
    0x02: 1, 0x04: 2, 0x06: 3, 0x08: 4, 0x0A: 5, 0x0C: 6,
}
LEGACY_AREA_WIDTHS = {
    0: 11,
    1: 5,
    2: 5,
    3: 5,
    4: 5,
    5: 7,
    6: 20,
    7: 20,
}

TITLE_WIDGET_NAMES = (
    "radio_title_header",
    "radio_source_box_1",
    "radio_source_box_2",
    "radio_source_box_3",
    "radio_title_text_label",
    "radio_tp_station_label",
    "radio_right_box_1",
    "radio_right_box_2",
    "radio_body_subtitle_label",
    "radio_body_text_label",
    "radio_footer_bar",
    "radio_date_label",
    "radio_time_label",
)


class RadioEmulator:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.window: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.ui_builder = None
        self._place_layouts: dict[str, dict[str, str]] = {}

        self.mode = "title"
        self.source = "analogue"
        self.source_label = "FMA"
        self.config = 0
        self.title = "FM 105.1"
        self.subtitle = ""
        self.status = "ST"
        self.right_indicators = ["ST"]
        self.body = ""
        self.hidden_header = False
        self.hidden_body = False
        self.backgrounded = False
        self.legacy_active = False
        self.legacy_areas = [""] * 8
        self.legacy_index_visible = False
        self.legacy_index_blocks: dict[int, str] = {}

        self.title_chars: list[str] = list(self.title)
        self.property_range: tuple[int, int] | None = None
        self.active_row = 0
        self.active_state = "highlight"
        self.select_items = ANALOGUE_SELECT[:]
        self.station_count = 0
        self.stations: list[str] = []
        self.selected_station = -1
        self.eq_values = {
            "Balance": 0,
            "Fader": 0,
            "Treble": 0,
            "Bass": 0,
        }

    def show(self, raw_frame: str = "") -> None:
        if self.window and self.window.winfo_exists():
            if raw_frame:
                self.consume_frame(raw_frame)
            self.window.lift()
            self.window.focus_force()
            self._render()
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("RADIO")
        self.window.resizable(False, False)
        self.window.configure(bg="#111111")
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        if not self._build_pygubu_ui():
            frame = tk.Frame(self.window, bg="#111111", padx=8, pady=8)
            frame.pack()
            self.canvas = tk.Canvas(
                frame,
                width=WIDTH,
                height=HEIGHT,
                bg="#1d2f38",
                highlightthickness=0,
            )
            self.canvas.pack()

        if raw_frame:
            self.consume_frame(raw_frame)
        self._render()

    def _build_pygubu_ui(self) -> bool:
        if pygubu is None or not UI_PATH.exists():
            return False

        try:
            builder = pygubu.Builder()
            builder.add_from_file(UI_PATH)
            builder.get_object("radio_frame", self.window)
            builder.import_widgets(self, user_named=True)
            self.canvas = self.radio_canvas
            self.ui_builder = builder
            self._remember_place_layouts()
            self._style_title_widgets()
        except Exception as exc:
            print(f"Unable to load Pygubu radio UI from {UI_PATH}: {exc}")
            if self.window is not None:
                for child in self.window.winfo_children():
                    child.destroy()
            self.canvas = None
            self.ui_builder = None
            self._place_layouts = {}
            return False

        return True

    def _remember_place_layouts(self) -> None:
        self._place_layouts = {}
        for name in TITLE_WIDGET_NAMES:
            widget = getattr(self, name, None)
            if widget is None:
                continue
            info = widget.place_info()
            if info:
                self._place_layouts[name] = dict(info)

    def _style_title_widgets(self) -> None:
        fonts = {
            "radio_source_box_1": ("TkDefaultFont", 13, "bold"),
            "radio_source_box_2": ("TkDefaultFont", 13, "bold"),
            "radio_source_box_3": ("TkDefaultFont", 13, "bold"),
            "radio_right_box_1": ("TkDefaultFont", 13, "bold"),
            "radio_right_box_2": ("TkDefaultFont", 13, "bold"),
            "radio_title_text_label": ("TkDefaultFont", 28, "bold"),
            "radio_tp_station_label": ("TkFixedFont", 11, "bold"),
            "radio_body_subtitle_label": ("TkDefaultFont", 15, "bold"),
            "radio_body_text_label": ("TkDefaultFont", 13),
            "radio_date_label": ("TkDefaultFont", 12),
            "radio_time_label": ("TkDefaultFont", 15),
        }
        for name, font in fonts.items():
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(font=font)

    def consume_frame(self, frame_text: str, sender: str = "", receiver: str = "", description: str = "") -> None:
        frame = self._parse_frame(frame_text)
        if len(frame) < 5:
            return

        sender_id, receiver_id, command = frame[0], frame[2], frame[3]
        if sender_id == 0x68 and receiver_id in (0x3B, 0x80, 0xFF):
            if command == 0x23:
                self._handle_title_text(frame)
            elif command == 0x24:
                self._handle_property_text(frame)
            elif command == 0x36:
                self._handle_eq(frame)
            elif command == 0x37:
                self._handle_tone_select(frame)
            elif command == 0x46:
                self._handle_radio_ui(frame)
            elif command == 0xD4:
                self._handle_station_list(frame)
            elif command == 0xA5:
                self._handle_legacy_area(frame)
            elif command == 0x21:
                self._handle_legacy_index(frame)
        elif sender_id == 0x3B and receiver_id == 0x68 and command == 0x45:
            self._handle_set_radio_ui(frame)

        self._render()

    def _close(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        self.canvas = None
        self._place_layouts = {}

    def _parse_frame(self, frame_text: str) -> list[int]:
        text = "".join(ch for ch in frame_text.upper() if ch in "0123456789ABCDEF")
        if len(text) < 10 or len(text) % 2:
            return []
        try:
            return [int(text[index:index + 2], 16) for index in range(0, len(text), 2)]
        except ValueError:
            return []

    def _decode_chars(self, data: list[int]) -> str:
        chars = []
        for byte in data:
            if byte == 0x00:
                break
            if byte == 0x06:
                chars.append("\n")
            elif 0x20 <= byte <= 0x7E:
                chars.append(chr(byte))
        return "".join(chars).strip()

    def _decode_legacy_text(self, data: list[int]) -> str:
        chars: list[str] = []
        discard = False
        for byte in data:
            if byte == 0x00:
                break
            if byte == 0x07:
                discard = True
                continue
            if byte == 0x08:
                discard = False
                continue
            if discard:
                continue
            if byte == 0x06:
                chars.append("\n")
            elif 0x20 <= byte <= 0x7E:
                chars.append(chr(byte))
        return "".join(chars).rstrip()

    def _set_source_from_layout(self, layout: int) -> None:
        self.config = layout & 0x1F
        self.source, self.source_label = SOURCE_META.get(layout & 0xE0, ("analogue", "RAD"))
        if self.source == "cdc":
            self.select_items = CDC_SELECT[:]
        elif self.source == "tape":
            self.select_items = TAPE_SELECT[:]
        else:
            self.select_items = ANALOGUE_SELECT[:]

    def _handle_title_text(self, frame: list[int]) -> None:
        if len(frame) < 7:
            return

        self.mode = "title"
        self.hidden_header = False
        self.hidden_body = False
        self.backgrounded = False
        self._set_source_from_layout(frame[4])

        visible: list[str] = []
        property_start: int | None = None
        property_end: int | None = None
        discard = False
        in_property = False
        for byte in frame[6:-1]:
            if byte == 0x00:
                break
            if byte == 0x07:
                discard = True
                continue
            if byte == 0x08:
                discard = False
                continue
            if byte == 0x03:
                in_property = True
                property_start = len(visible)
                continue
            if byte == 0x04:
                in_property = False
                property_end = len(visible)
                continue
            if discard:
                continue
            if byte == 0x06:
                visible.append("\n")
            elif 0x20 <= byte <= 0x7E:
                visible.append(chr(byte))

        self.title_chars = visible
        if property_start is not None:
            self.property_range = (property_start, property_end if property_end is not None else len(visible))
        else:
            self.property_range = None

        raw_title = "".join(visible).strip()
        if frame[4] == 0x62:
            self._set_legacy_area(0, raw_title, activate=False)
        self._apply_title_text(raw_title)

    def _handle_property_text(self, frame: list[int]) -> None:
        if len(frame) < 7:
            return

        self._set_source_from_layout(frame[4])
        replacement = self._decode_chars(frame[6:-1])
        if self.property_range is not None:
            start, end = self.property_range
            self.title_chars = self.title_chars[:start] + list(replacement) + self.title_chars[end:]
            self.property_range = (start, start + len(replacement))
            self._apply_title_text("".join(self.title_chars).strip())
        elif replacement:
            self._apply_title_text(replacement)
        if self.legacy_active and self.source == "digital":
            self._set_legacy_area(0, self.title, activate=False)
        self.mode = "title"

    def _handle_legacy_area(self, frame: list[int]) -> None:
        payload = frame[4:-1]
        if len(payload) >= 3 and payload[0] == 0x62 and payload[1] == 0x01:
            area = payload[2]
            if 1 <= area <= 7:
                self._set_legacy_area(area, self._decode_legacy_text(payload[3:]))
                self.mode = "title"
                self.hidden_header = False
                self.hidden_body = False
                self.backgrounded = False
            return

        if len(payload) >= 3 and payload[0] == 0x60 and payload[1] == 0x01 and payload[2] == 0x00:
            self.legacy_active = True
            self.legacy_index_visible = not self.legacy_index_visible
            self.mode = "title"

    def _handle_legacy_index(self, frame: list[int]) -> None:
        payload = frame[4:-1]
        if len(payload) < 3 or payload[0] != 0x60 or payload[1] != 0x00:
            return

        index_area = payload[2]
        text = self._decode_legacy_text(payload[3:])
        if text:
            self.legacy_index_blocks[index_area] = text
        else:
            self.legacy_index_blocks.pop(index_area, None)
        self.legacy_active = True
        self.mode = "title"

    def _set_legacy_area(self, area: int, text: str, activate: bool = True) -> None:
        if not 0 <= area < len(self.legacy_areas):
            return
        width = LEGACY_AREA_WIDTHS.get(area)
        self.legacy_areas[area] = text[:width] if width else text
        if activate:
            self.legacy_active = True

    def _apply_title_text(self, text: str) -> None:
        normalized = " ".join(text.split())
        if not normalized:
            return

        if self.source == "analogue":
            if normalized.endswith(" ST"):
                self.status = "ST"
                normalized = normalized[:-3].rstrip()
            elif self.config & 0x10:
                self.status = "ST"
            else:
                self.status = ""
        elif self.source == "cdc":
            self.status = ""
        elif self.source == "digital":
            self.status = "FMD"
        elif self.source == "tape":
            self.status = "SIDE B" if self.config & 0x10 else "SIDE A"

        self._update_right_indicators()
        self.title = normalized
        self.subtitle = self._config_text()

    def _update_right_indicators(self) -> None:
        if self.source == "digital":
            indicators = []
            if self.config in (0x01, 0x02):
                indicators.append("RDS")
            else:
                indicators.append("TP")
                indicators.append("RDS")
            self.right_indicators = indicators[:2]
        elif self.source == "analogue":
            indicators = []
            if self.config & 0x08:
                indicators.append("TP")
            if self.status:
                indicators.append(self.status)
            self.right_indicators = indicators[:2] or [""]
        elif self.source == "tape":
            self.right_indicators = [self.status]
        elif self.source == "cdc":
            self.right_indicators = ["CD"]
        elif self.source == "traffic":
            self.right_indicators = ["TP"]
        else:
            self.right_indicators = [self.status or self.source_label]

    def _config_text(self) -> str:
        if self.source == "analogue":
            return {
                0x01: "Manual station choice",
                0x02: "Station sample",
                0x03: "Search sensitive",
                0x04: "Search non sensitive",
                0x06: "Traffic",
                0x07: "Traffic program",
            }.get(self.config & 0x07, "")
        if self.source == "cdc":
            return {
                0x00: "CD ERROR",
                0x01: "NO MAGAZINE",
                0x02: "NO DISC",
                0x03: "CD CHECK",
                0x04: "Music search",
                0x05: "Fast forward",
                0x06: "Rewind",
                0x07: "Track sample",
                0x08: "Random generator",
                0x0A: "Fast forward/reverse",
                0x0B: "Loading",
            }.get(self.config, "")
        if self.source == "digital":
            return {
                0x00: "Stations / Info",
                0x01: "RDS",
                0x02: "Header",
                0x03: "MP3",
            }.get(self.config, "")
        if self.source == "tape":
            return {
                0x00: "TAPE ERROR",
                0x02: "Tape present",
                0x03: "Fast forward",
                0x04: "Fast rewind",
                0x06: "Forward",
                0x07: "Rewind",
                0x08: "Clean",
                0x09: "Inverse",
            }.get(self.config & 0x0F, "")
        return ""

    def _tp_station_text(self) -> str:
        if self.source != "digital" or not self.title.strip():
            return ""
        return f"TP-Station: {self.title.strip()}"

    def _handle_eq(self, frame: list[int]) -> None:
        if len(frame) < 6:
            return

        byte = frame[4]
        prop = byte & 0xE0
        value = byte & 0x1F
        self.mode = "tone"
        self.hidden_body = False
        if prop == 0x40 and value in BALANCE_VALUES:
            self.eq_values["Balance"] = BALANCE_VALUES[value]
            self.active_row = 3
        elif prop == 0x60 and value in TONE_VALUES:
            self.eq_values["Bass"] = TONE_VALUES[value]
            self.active_row = 0
        elif prop == 0x80 and value in FADER_VALUES:
            self.eq_values["Fader"] = FADER_VALUES[value]
            self.active_row = 2
        elif prop == 0xC0 and value in TONE_VALUES:
            self.eq_values["Treble"] = TONE_VALUES[value]
            self.active_row = 1

    def _handle_tone_select(self, frame: list[int]) -> None:
        if len(frame) < 6:
            return

        command = frame[4]
        function = command & 0xC0
        row = (command & 0x30) >> 4
        self.active_row = row
        self.hidden_body = False

        if function == 0x80:
            self.mode = "tone"
            self._apply_tone_value("Bass", command & 0x1F)
            if len(frame) >= 9:
                self._apply_tone_value("Treble", frame[5] & 0x1F)
                self._apply_tone_value("Fader", frame[6] & 0x1F)
                self._apply_tone_value("Balance", frame[7] & 0x1F)
        elif function == 0xC0:
            self.mode = "tone"
        else:
            self.mode = "select"
            if function == 0x00:
                self.source = "cdc" if command & 0x08 else "analogue"
                self.source_label = "CDC" if self.source == "cdc" else "FMD"
                self.active_state = "active" if (command & 0x07) == 0x05 else "highlight"
            else:
                self.active_state = "highlight"
            self.select_items = CDC_SELECT[:] if self.source == "cdc" else ANALOGUE_SELECT[:]

    def _apply_tone_value(self, name: str, value: int) -> None:
        if name == "Balance" and value in BALANCE_VALUES:
            self.eq_values[name] = BALANCE_VALUES[value]
        elif name == "Fader" and value in FADER_VALUES:
            self.eq_values[name] = FADER_VALUES[value]
        elif value in TONE_VALUES:
            self.eq_values[name] = TONE_VALUES[value]

    def _handle_radio_ui(self, frame: list[int]) -> None:
        if len(frame) < 6:
            return
        flags = frame[4]
        self.backgrounded = bool(flags & 0x01)
        self.hidden_header = bool(flags & 0x02)
        self.hidden_body = bool(flags & 0x0C)
        if flags & 0x0C:
            self.mode = "title"

    def _handle_set_radio_ui(self, frame: list[int]) -> None:
        if len(frame) < 6:
            return
        flags = frame[4]
        self.backgrounded = bool(flags & 0x01)

    def _handle_station_list(self, frame: list[int]) -> None:
        if len(frame) < 8 or frame[4] != 0x03:
            return

        self.mode = "station_list"
        self.source = "digital"
        self.source_label = "FMD"
        self.right_indicators = ["TP", "RDS"]
        self.station_count = frame[5]
        message_index = frame[6]
        offset = message_index * 3
        while len(self.stations) < self.station_count:
            self.stations.append("")

        entries = self._parse_station_entries(frame[7:-1])
        for idx, (name, selected) in enumerate(entries):
            absolute = offset + idx
            if absolute < self.station_count:
                self.stations[absolute] = name
                if selected:
                    self.selected_station = absolute
                    self.title = name

    def _parse_station_entries(self, data: list[int]) -> list[tuple[str, bool]]:
        entries: list[tuple[str, bool]] = []
        current: list[int] = []
        for byte in data:
            if byte in (0x00, 0x10):
                if current:
                    entries.append((self._decode_chars(current), byte == 0x10))
                    current = []
            else:
                current.append(byte)
        if current:
            entries.append((self._decode_chars(current), False))
        return entries

    def _render(self) -> None:
        if self.canvas is None:
            return
        canvas = self.canvas

        if self.backgrounded:
            self._show_canvas()
            canvas.delete("all")
            self._draw_backgrounded(canvas)
            return

        if self.mode == "select":
            self._show_canvas()
            canvas.delete("all")
            self._draw_select(canvas)
        elif self.mode == "tone":
            self._show_canvas()
            canvas.delete("all")
            self._draw_tone(canvas)
        elif self.mode == "station_list":
            self._show_canvas()
            canvas.delete("all")
            self._draw_station_list(canvas)
        elif self.legacy_active:
            if not self._render_title_widgets(legacy=True):
                self._show_canvas()
                canvas.delete("all")
                self._draw_legacy_title(canvas)
        else:
            if not self._render_title_widgets(legacy=False):
                self._show_canvas()
                canvas.delete("all")
                self._draw_title(canvas)

    def _show_canvas(self) -> None:
        if hasattr(self, "radio_canvas"):
            self.radio_canvas.tkraise()

    def _set_place_visible(self, name: str, visible: bool) -> None:
        widget = getattr(self, name, None)
        if widget is None:
            return
        if visible:
            layout = self._place_layouts.get(name)
            if layout and not widget.winfo_manager():
                widget.place(**layout)
        elif widget.winfo_manager():
            widget.place_forget()

    def _render_title_widgets(self, legacy: bool) -> bool:
        if not hasattr(self, "radio_title_view"):
            return False
        if legacy and self.legacy_index_visible and self.legacy_index_blocks:
            return False

        self.radio_title_view.tkraise()
        bg = "#8a969d" if legacy else "#89959b"
        self.radio_title_view.configure(bg=bg)
        for name in ("radio_body_subtitle_label", "radio_body_text_label"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(bg=bg)

        self._set_place_visible("radio_title_header", not self.hidden_header)
        self._set_place_visible("radio_body_subtitle_label", not self.hidden_body)
        self._set_place_visible("radio_body_text_label", not self.hidden_body)

        if legacy:
            left_values = [
                self.legacy_areas[1].strip() or self.source_label,
                self.legacy_areas[2].strip(),
                self.legacy_areas[3].strip(),
            ]
            right_values = [
                self.legacy_areas[4].strip() or (self.right_indicators[0] if self.right_indicators else ""),
                self.legacy_areas[5].strip() or (self.right_indicators[1] if len(self.right_indicators) > 1 else ""),
            ]
            title = (self.legacy_areas[0].strip() or self.title)[:18]
            body_1 = self.legacy_areas[6].rstrip()[:20]
            body_2 = self.legacy_areas[7].rstrip()[:20]
            tp_station = ""
        else:
            left_values = [self.source_label, "", ""]
            right_values = (self.right_indicators[:2] or [""]) + ["", ""]
            title = self.title[:18]
            body_1 = self.subtitle[:34]
            body_2 = self.body[:42]
            tp_station = self._tp_station_text()[:28]

        for index, value in enumerate(left_values[:3], start=1):
            getattr(self, f"radio_source_box_{index}").configure(text=value)
        self.radio_right_box_1.configure(text=right_values[0][:7])
        self.radio_right_box_2.configure(text=right_values[1][:7])
        self.radio_title_text_label.configure(text=title)
        self.radio_tp_station_label.configure(text=tp_station)
        self.radio_body_subtitle_label.configure(text=body_1)
        self.radio_body_text_label.configure(text=body_2)
        self.radio_date_label.configure(text=time.strftime("%m/%d/%Y"))
        self.radio_time_label.configure(text=time.strftime("%H:%M:%S"))
        return True

    def _draw_backgrounded(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#111111", outline="")

    def _draw_title(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#89959b", outline="#141414", width=2)
        header_h = 78
        if not self.hidden_header:
            canvas.create_rectangle(0, 0, WIDTH, header_h, fill="#87969d", outline="#111111", width=2)
            canvas.create_rectangle(0, 0, 66, 26, fill="#dcecf1", outline="#111111")
            canvas.create_rectangle(0, 26, 66, 52, fill="#dcecf1", outline="#111111")
            canvas.create_rectangle(0, 52, 66, header_h, fill="#dcecf1", outline="#111111")
            canvas.create_text(12, 13, text=self.source_label, fill="#111111", anchor="w", font=("TkDefaultFont", 13, "bold"))

            indicators = self.right_indicators[:2] or [""]
            box_h = 26
            for index, text in enumerate(indicators):
                top = index * box_h
                canvas.create_rectangle(316, top, WIDTH, top + box_h, fill="#eef3f7", outline="#111111")
                canvas.create_text(358, top + 13, text=text, fill="#111111", anchor="center", font=("TkDefaultFont", 13, "bold"))
            if len(indicators) == 1:
                canvas.create_rectangle(316, box_h, WIDTH, box_h * 2, fill="#eef3f7", outline="#111111")
            canvas.create_text(200, 32, text=self.title[:18], fill="#f28a60", anchor="center", font=("TkDefaultFont", 28, "bold"))
            tp_station = self._tp_station_text()
            if tp_station:
                canvas.create_text(200, 62, text=tp_station[:28], fill="#f28a60", anchor="center", font=("TkFixedFont", 11, "bold"))
        if not self.hidden_body:
            if self.subtitle:
                canvas.create_text(24, 108, text=self.subtitle[:34], fill="#1f2e34", anchor="w", font=("TkDefaultFont", 15, "bold"))
            if self.body:
                canvas.create_text(24, 140, text=self.body[:42], fill="#1f2e34", anchor="w", font=("TkDefaultFont", 13))

        now = time.strftime("%H:%M:%S")
        canvas.create_rectangle(0, HEIGHT - 25, WIDTH, HEIGHT, fill="#f5f2e9", outline="")
        canvas.create_text(14, HEIGHT - 13, text=time.strftime("%m/%d/%Y"), fill="#1d1d1d", anchor="w", font=("TkDefaultFont", 12))
        canvas.create_text(WIDTH - 12, HEIGHT - 13, text=now, fill="#1d1d1d", anchor="e", font=("TkDefaultFont", 16))

    def _draw_legacy_title(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#8a969d", outline="#141414", width=2)
        header_h = 78

        if not self.hidden_header:
            canvas.create_rectangle(0, 0, WIDTH, header_h, fill="#87969d", outline="#111111", width=2)
            for index in range(3):
                top = index * 26
                text = self.legacy_areas[index + 1].strip()
                if index == 0 and not text:
                    text = self.source_label
                canvas.create_rectangle(0, top, 66, top + 26, fill="#dcecf1", outline="#111111")
                canvas.create_text(33, top + 13, text=text[:5], fill="#111111", anchor="center", font=("TkDefaultFont", 13, "bold"))

            right_values = [
                self.legacy_areas[4].strip() or (self.right_indicators[0] if self.right_indicators else ""),
                self.legacy_areas[5].strip() or (self.right_indicators[1] if len(self.right_indicators) > 1 else ""),
            ]
            for index, text in enumerate(right_values):
                top = index * 26
                canvas.create_rectangle(316, top, WIDTH, top + 26, fill="#eef3f7", outline="#111111")
                canvas.create_text(358, top + 13, text=text[:7], fill="#111111", anchor="center", font=("TkDefaultFont", 13, "bold"))

            title = self.legacy_areas[0].strip() or self.title
            canvas.create_text(200, 39, text=title[:18], fill="#f28a60", anchor="center", font=("TkDefaultFont", 26, "bold"))

        if not self.hidden_body:
            line6 = self.legacy_areas[6].rstrip()
            line7 = self.legacy_areas[7].rstrip()
            if line6:
                canvas.create_text(86, 111, text=line6[:20], fill="#1f2e34", anchor="w", font=("TkFixedFont", 18, "bold"))
            if line7:
                canvas.create_text(86, 147, text=line7[:20], fill="#1f2e34", anchor="w", font=("TkFixedFont", 18, "bold"))
            if self.legacy_index_visible and self.legacy_index_blocks:
                self._draw_legacy_index(canvas)

        canvas.create_rectangle(0, HEIGHT - 25, WIDTH, HEIGHT, fill="#f5f2e9", outline="")
        canvas.create_text(14, HEIGHT - 13, text=time.strftime("%m/%d/%Y"), fill="#1d1d1d", anchor="w", font=("TkDefaultFont", 12))
        canvas.create_text(WIDTH - 12, HEIGHT - 13, text=time.strftime("%H:%M:%S"), fill="#1d1d1d", anchor="e", font=("TkDefaultFont", 15))

    def _draw_legacy_index(self, canvas: tk.Canvas) -> None:
        labels: list[str] = []
        for key in sorted(self.legacy_index_blocks):
            labels.extend(part.strip() for part in self.legacy_index_blocks[key].splitlines() if part.strip())
        labels = labels[:6]
        if not labels:
            return

        canvas.create_rectangle(10, 160, WIDTH - 10, HEIGHT - 32, fill="#263d46", outline="#d7e6ea", width=2)
        for index, label in enumerate(labels):
            col = index % 2
            row = index // 2
            x = 26 + col * 188
            y = 174 + row * 19
            canvas.create_text(x, y, text=label[:14], fill="#f1f5d6", anchor="w", font=("TkDefaultFont", 12, "bold"))

    def _draw_select(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#b7b8b8", outline="")
        canvas.create_rectangle(0, 0, WIDTH, 62, fill="#e6e6e6", outline="")
        canvas.create_text(10, 30, text=self.title[:12], fill="#000000", anchor="w", font=("TkDefaultFont", 31, "bold"))
        canvas.create_text(214, 35, text=self._active_symbol(), fill="#000000", anchor="center", font=("TkDefaultFont", 14, "bold"))
        indicators = self.right_indicators[:2] or [self.status or "P4", self.source_label]
        canvas.create_text(WIDTH - 16, 18, text=indicators[0] if len(indicators) > 0 else "", fill="#000000", anchor="e", font=("TkDefaultFont", 12, "bold"))
        canvas.create_text(WIDTH - 16, 43, text=indicators[1] if len(indicators) > 1 else self.source_label, fill="#000000", anchor="e", font=("TkDefaultFont", 12, "bold"))

        render_items = list(reversed(self.select_items))
        row_h = 36
        y0 = 74
        active_from_top = len(render_items) - 1 - min(self.active_row, len(render_items) - 1)
        for index, (symbol, text) in enumerate(render_items):
            y = y0 + index * row_h
            is_active = index == active_from_top
            if is_active:
                fill = "#d9d9d9" if self.active_state == "highlight" else "#f1a640"
                canvas.create_rectangle(8, y - 3, 132, y + 27, fill=fill, outline="#000000", width=2)
            canvas.create_text(18, y + 11, text=symbol, fill="#ffffff" if not is_active else "#000000", anchor="w", font=("TkDefaultFont", 16, "bold"))
            canvas.create_text(150, y + 11, text=text, fill="#ffffff", anchor="w", font=("TkDefaultFont", 15, "bold"))

    def _draw_tone(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#20384a", outline="")
        canvas.create_rectangle(0, 0, WIDTH, 64, fill="#38556d", outline="")
        canvas.create_text(12, 32, text=self.title[:12], fill="#eaf3f7", anchor="w", font=("TkDefaultFont", 29, "bold"))
        indicators = self.right_indicators[:2] or [self.status or "P1", self.source_label]
        canvas.create_text(WIDTH - 14, 18, text=indicators[0] if len(indicators) > 0 else "", fill="#eaf3f7", anchor="e", font=("TkDefaultFont", 12, "bold"))
        canvas.create_text(WIDTH - 14, 43, text=indicators[1] if len(indicators) > 1 else self.source_label, fill="#eaf3f7", anchor="e", font=("TkDefaultFont", 12, "bold"))

        y0 = 86
        row_h = 32
        for index, name in enumerate(["Balance", "Fader", "Treble", "Bass"]):
            y = y0 + index * row_h
            active = self.active_row == TONE_ROWS.index(name)
            color = "#ff8f8f" if active else "#dbe8ee"
            canvas.create_text(22, y, text=name, fill=color, anchor="w", font=("TkDefaultFont", 15, "bold"))
            self._draw_bar(canvas, 164, y, self.eq_values[name], name, active)

    def _draw_bar(self, canvas: tk.Canvas, x: int, y: int, value: int, name: str, active: bool) -> None:
        left_label, right_label = ("min", "max")
        if name == "Balance":
            left_label, right_label = ("Left", "Right")
        elif name == "Fader":
            left_label, right_label = ("Rear", "Front")
        canvas.create_text(x - 54, y, text=left_label, fill="#ffffff", anchor="w", font=("TkDefaultFont", 13, "bold"))
        canvas.create_text(x + 164, y, text=right_label, fill="#ffffff", anchor="w", font=("TkDefaultFont", 13, "bold"))
        canvas.create_rectangle(x, y - 4, x + 132, y + 4, fill="#0f78ae", outline="")
        canvas.create_line(x + 66, y - 10, x + 66, y + 10, fill="#80a9c2")
        max_abs = 10 if name in ("Balance", "Fader") else 6
        pos = int((value + max_abs) / (max_abs * 2) * 132)
        marker = "#ff8f8f" if active else "#dbe8ee"
        canvas.create_rectangle(x + pos - 5, y - 6, x + pos + 5, y + 6, fill=marker, outline="")

    def _draw_station_list(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#223238", outline="")
        canvas.create_rectangle(0, 0, WIDTH, 74, fill="#899b9c", outline="")
        canvas.create_text(12, 22, text=self.subtitle or self.title[:12], fill="#eaffd8", anchor="w", font=("TkDefaultFont", 19, "bold"))
        canvas.create_text(156, 23, text=self.source_label, fill="#eaffd8", anchor="w", font=("TkDefaultFont", 18, "bold"))
        canvas.create_text(WIDTH - 14, 19, text=self.right_indicators[0] if self.right_indicators else "", fill="#eaffd8", anchor="e", font=("TkDefaultFont", 13, "bold"))
        canvas.create_text(WIDTH - 14, 42, text=self.right_indicators[1] if len(self.right_indicators) > 1 else "", fill="#eaffd8", anchor="e", font=("TkDefaultFont", 13, "bold"))
        canvas.create_text(12, 56, text=(self.title or "Stations")[:18], fill="#eaffd8", anchor="w", font=("TkDefaultFont", 31, "bold"))

        visible = self.stations[:6]
        for index, name in enumerate(visible):
            y = 89 + index * 23
            selected = index == self.selected_station
            if selected:
                canvas.create_rectangle(10, y - 13, 290, y + 10, fill="#7e5a28", outline="#ff9f24", width=2)
            canvas.create_text(24, y, text=name[:14], fill="#f0f8d4", anchor="w", font=("TkFixedFont", 18, "bold"))
        canvas.create_rectangle(0, HEIGHT - 24, WIDTH, HEIGHT, fill="#84aab3", outline="")
        canvas.create_text(WIDTH - 14, HEIGHT - 12, text="TMC", fill="#9ee34a", anchor="e", font=("TkDefaultFont", 14, "bold"))

    def _active_symbol(self) -> str:
        if not self.select_items:
            return ""
        row = min(self.active_row, len(self.select_items) - 1)
        symbol = self.select_items[row][0]
        if self.active_state == "active" and symbol in ("m", "II", "I"):
            return f"< {symbol} >"
        return symbol
