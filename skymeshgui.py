"""Graphical companion for Skymeshgui.py.

This file keeps the terminal tracker available for comparison while adding
mouse-based event selection through the standard-library Tkinter GUI.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import ctypes
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Tuple

import SkyandSeaAlertLocal as tracker


Event = Dict[str, str]
WorkResult = Tuple[str, Any]
CHANNELS = (
    "0 LongFast",
    "1 MediumFast",
    "2 Luminous",
    "3 TheMatrix",
    "4 FloridaMesh",
    "5 Weather",
    "6 Emergency",
    "7 BBS",
)
NODES = (
    "1: Node1",
    "2: Node2",
)


class SkyAndSeaGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sky Alert")
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sky-alert.ico")
        if os.path.isfile(icon_path):
            self.root.iconbitmap(icon_path)
        self.root.geometry("900x500")
        self.events: List[Event] = []
        self.results: "queue.Queue[WorkResult]" = queue.Queue()
        self.scan_in_progress = False
        self.send_in_progress = False
        self.dark_mode = True

        self.node_var = tk.StringVar(value=NODES[int(tracker.selected_node) - 1])
        self.channel_var = tk.StringVar(value=CHANNELS[tracker.selected_channel])
        self.status_var = tk.StringVar(value="Ready")
        self.api_logging_var = tk.BooleanVar(value=tracker.API_LOGGING)

        self.style = ttk.Style(self.root)
        self._build_widgets()
        self._apply_theme()
        self.root.after(100, self._poll_results)
        self._start_scan()

    def _build_widgets(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Node:").pack(side=tk.LEFT)
        node_box = ttk.Combobox(
            controls,
            textvariable=self.node_var,
            values=NODES,
            state="readonly",
            width=22,
        )
        node_box.pack(side=tk.LEFT, padx=(5, 15))
        node_box.bind("<<ComboboxSelected>>", self._node_changed)

        ttk.Label(controls, text="Channel:").pack(side=tk.LEFT)
        channel_box = ttk.Combobox(
            controls,
            textvariable=self.channel_var,
            values=CHANNELS,
            state="readonly",
            width=18,
        )
        channel_box.pack(side=tk.LEFT, padx=(5, 15))
        channel_box.bind("<<ComboboxSelected>>", self._channel_changed)

        self.scan_button = ttk.Button(controls, text="Refresh", command=self._start_scan)
        self.scan_button.pack(side=tk.RIGHT)
        self.theme_button = ttk.Button(
            controls,
            text="Dark mode",
            command=self._toggle_theme,
        )
        self.theme_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.log_button = ttk.Button(
            controls,
            text="View API log",
            command=self._show_api_log,
        )
        self.log_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.response_log_button = ttk.Button(
            controls,
            text="View API output",
            command=self._show_api_output,
        )
        self.response_log_button.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Checkbutton(
            controls,
            text="Log API calls",
            variable=self.api_logging_var,
            command=self._toggle_api_logging,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        list_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        list_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            list_frame,
            text="Double-click an aircraft or vessel to send it to the selected node.",
        ).pack(anchor=tk.W, pady=(0, 5))

        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        self.event_list = tk.Listbox(list_container, activestyle="dotbox")
        self.event_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(
            list_container,
            orient=tk.VERTICAL,
            command=self.event_list.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.event_list.configure(yscrollcommand=scrollbar.set)
        self.event_list.bind("<Double-Button-1>", self._send_selected)
        self.event_list.bind("<Return>", self._send_selected)

        footer = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Send Selected", command=self._send_selected).pack(
            side=tk.LEFT
        )
        ttk.Label(footer, textvariable=self.status_var).pack(
            side=tk.LEFT, padx=15
        )

    def _toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def _toggle_api_logging(self) -> None:
        tracker.set_api_logging(self.api_logging_var.get())
        state = "enabled" if self.api_logging_var.get() else "disabled"
        self.status_var.set(f"API logging {state}.")

    def _show_api_log(self) -> None:
        log_window = tk.Toplevel(self.root)
        log_window.title("Sky and Sea API log")
        log_window.geometry("1000x500")
        log_background = "#303134" if self.dark_mode else "#ffffff"
        log_foreground = "#f1f3f4" if self.dark_mode else "#202124"
        log_text = tk.Text(
            log_window,
            wrap=tk.NONE,
            background=log_background,
            foreground=log_foreground,
            insertbackground=log_foreground,
        )
        log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        try:
            with open(tracker.API_LOG_FILE, encoding="utf-8") as log_file:
                contents = self._format_api_log(log_file)
        except FileNotFoundError:
            contents = "No API log entries yet. Enable logging and refresh the feeds."
        except OSError as exc:
            contents = f"Unable to read API log: {exc}"
        log_text.insert("1.0", contents)
        log_text.configure(state=tk.DISABLED)

    def _show_api_output(self) -> None:
        log_window = tk.Toplevel(self.root)
        log_window.title("Sky and Sea API output")
        log_window.geometry("1100x650")
        log_background = "#303134" if self.dark_mode else "#ffffff"
        log_foreground = "#f1f3f4" if self.dark_mode else "#202124"
        log_text = tk.Text(
            log_window,
            wrap=tk.NONE,
            background=log_background,
            foreground=log_foreground,
            insertbackground=log_foreground,
        )
        log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        try:
            with open(tracker.API_RESPONSE_LOG_FILE, encoding="utf-8") as log_file:
                contents = self._format_api_output(log_file)
        except FileNotFoundError:
            contents = "No API output entries yet. Enable logging and refresh the feeds."
        except OSError as exc:
            contents = f"Unable to read API output log: {exc}"
        log_text.insert("1.0", contents)
        log_text.configure(state=tk.DISABLED)

    @staticmethod
    def _format_api_output(log_file: Any) -> str:
        formatted: List[str] = []
        for line_number, line in enumerate(log_file, start=1):
            try:
                entry = json.loads(line)
                response = json.dumps(
                    entry.get("response"),
                    ensure_ascii=False,
                    indent=2,
                )
                formatted.append(
                    "\n".join(
                        [
                            f"{'=' * 72}",
                            f"{entry.get('ts', '?')}  {entry.get('api', 'API')}",
                            entry.get("url", "?"),
                            response,
                        ]
                    )
                )
            except json.JSONDecodeError:
                formatted.append(f"[Entry {line_number}] {line.strip()}")
        return "\n".join(formatted) or "No API output entries yet."

    @staticmethod
    def _format_api_log(log_file: Any) -> str:
        formatted: List[str] = []
        for line_number, line in enumerate(log_file, start=1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                formatted.append(f"[Entry {line_number}] {line.strip()}")
                continue

            status = entry.get("status", "ERROR")
            outcome = "OK" if isinstance(status, int) and status < 400 else "ERROR"
            formatted.append(
                "\n".join(
                    [
                        f"{'=' * 72}",
                        f"{outcome}  {entry.get('ts', '?')}  {entry.get('api', 'API')}",
                        f"{entry.get('method', '?')} {entry.get('url', '?')}",
                        f"Status: {status}    Duration: {entry.get('duration_ms', '?')} ms"
                        f"    Bytes: {entry.get('bytes', '?')}",
                        f"Error: {entry['error']}"
                        if entry.get("error")
                        else "Response: received",
                    ]
                )
            )
        return "\n".join(formatted) or "No API log entries yet."

    def _apply_theme(self) -> None:
        if self.dark_mode:
            background = "#202124"
            foreground = "#f1f3f4"
            field_background = "#303134"
            select_background = "#3c78d8"
            self.theme_button.configure(text="Normal mode")
        else:
            background = "#f0f0f0"
            foreground = "#202124"
            field_background = "#ffffff"
            select_background = "#b4d7ff"
            self.theme_button.configure(text="Dark mode")

        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.root.configure(background=background)
        self.style.configure("TFrame", background=background)
        self.style.configure("TLabel", background=background, foreground=foreground)
        self.style.configure(
            "TCheckbutton",
            background=background,
            foreground=foreground,
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", background)],
            foreground=[("active", foreground)],
        )
        self.style.configure(
            "TButton",
            background=field_background,
            foreground=foreground,
            bordercolor=field_background,
            lightcolor=field_background,
            darkcolor=field_background,
            padding=(8, 4),
        )
        self.style.map(
            "TButton",
            background=[
                ("disabled", background),
                ("active", select_background),
                ("pressed", select_background),
            ],
            foreground=[
                ("disabled", "#808080"),
                ("active", foreground),
                ("pressed", foreground),
            ],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=field_background,
            background=field_background,
            foreground=foreground,
            arrowcolor=foreground,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", field_background)],
            foreground=[("readonly", foreground)],
        )
        self.event_list.configure(
            background=field_background,
            foreground=foreground,
            selectbackground=select_background,
            selectforeground=foreground,
        )
        self._apply_windows_titlebar(self.dark_mode)

    def _apply_windows_titlebar(self, dark: bool) -> None:
        if sys.platform != "win32":
            return
        self.root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        use_dark_mode = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(use_dark_mode),
                ctypes.sizeof(use_dark_mode),
            )
            if result == 0:
                break

    def _node_changed(self, *_args: Any) -> None:
        tracker.selected_node = self.node_var.get().split(":", 1)[0]

    def _channel_changed(self, *_args: Any) -> None:
        tracker.selected_channel = CHANNELS.index(self.channel_var.get())

    def _start_scan(self) -> None:
        if self.scan_in_progress:
            return
        self.scan_in_progress = True
        self.scan_button.configure(state=tk.DISABLED)
        self.status_var.set("Scanning feeds...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        self.results.put(("scan", tracker._scan()))

    def _send_selected(self, *_args: Any) -> str:
        selection = self.event_list.curselection()
        if not selection:
            self.status_var.set("Select an event first.")
            return "break"
        if self.send_in_progress:
            return "break"

        event = self.events[selection[0]]
        self.send_in_progress = True
        self.status_var.set("Sending...")
        threading.Thread(target=self._send_worker, args=(event,), daemon=True).start()
        return "break"

    @staticmethod
    def _aircraft_distance(event: Event) -> float:
        match = re.search(r"Distance:\s*([\d.]+)\s*mi", event.get("message", ""))
        return float(match.group(1)) if match else float("inf")

    def _sort_aircraft_by_distance(self) -> None:
        aircraft = [
            event for event in self.events if event.get("kind") == "aircraft"
        ]
        aircraft.sort(key=self._aircraft_distance)
        aircraft_index = iter(aircraft)
        self.events = [
            next(aircraft_index) if event.get("kind") == "aircraft" else event
            for event in self.events
        ]

    def _send_worker(self, event: Event) -> None:
        try:
            tracker._send_event(event)
        except (ImportError, OSError, RuntimeError) as exc:
            self.results.put(("send_error", str(exc)))
        else:
            self.results.put(("sent", event["display"]))

    def _poll_results(self) -> None:
        try:
            while True:
                result_type, payload = self.results.get_nowait()
                if result_type == "scan":
                    self.events = payload
                    self._sort_aircraft_by_distance()
                    self.event_list.delete(0, tk.END)
                    for number, event in enumerate(self.events, start=1):
                        self.event_list.insert(tk.END, f"{number:02d}. {event['display']}")
                    self.scan_in_progress = False
                    self.scan_button.configure(state=tk.NORMAL)
                    self.status_var.set(f"Found {len(self.events)} event(s).")
                elif result_type == "sent":
                    self.send_in_progress = False
                    self.status_var.set("Message sent.")
                else:
                    self.send_in_progress = False
                    self.status_var.set("Send failed.")
                    messagebox.showerror("Send failed", payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)


def main() -> int:
    tracker._configure_output()
    root = tk.Tk()
    SkyAndSeaGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
