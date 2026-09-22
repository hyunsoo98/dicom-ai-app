"""Desktop console UI for the X-ray source simulator.

A from-scratch Tkinter UI (no copied layouts, icons, or screenshots from any
real product - see pipeline/PLAN.md section 3-1). Lets a user drive the
simulator's kVp/mA/mode/brightness/contrast/zoom/flip and trigger captures.

Beyond the basic controls, this adds:
- A "compare" pair of panels: the console's own PNG preview of a capture,
  next to the same capture *decoded back from the actual DICOM file* that
  was (or would be) sent to a viewer - an independent round-trip check
  that the DICOM encoding didn't corrupt or misrepresent the image, not
  just two views of the same in-memory array.
- A horizontally scrollable filmstrip of every capture taken this session,
  click to load it into the compare panels, click-and-drag to pan.

Usage:
    python ../simulator/source_simulator.py --port 5588   # terminal 1
    python console_app.py --port 5588                     # terminal 2
"""

from __future__ import annotations

import argparse
import queue
import socket
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.imaging import load_capture_preview, load_dicom_preview
from common.protocol import Command, Frame, PacketStreamParser, encode

MODES = ("FLUORO", "RADIOGRAPHY", "PULSED", "LOW_DOSE")
EXPOSURE_COLORS = {"OFF": "#666666", "READY": "#2a7a2a", "EXPOSING": "#c0392b"}
THUMB_SIZE = (88, 88)
COMPARE_SIZE = (360, 360)
DRAG_CLICK_THRESHOLD = 5  # px; below this, a press+release is a click, not a pan


@dataclass
class CaptureRecord:
    index: int
    png_path: str
    dicom_path: str
    dose_factor: float
    thumb_photo: object = None  # ImageTk.PhotoImage, kept alive here
    widget: object = None


class SimulatorLink:
    """Owns the TCP socket; runs the reader in a background thread and
    hands received frames to the UI thread via a queue (Tkinter widgets
    are not thread-safe, so nothing here touches the UI directly).
    """

    def __init__(self, host: str, port: int, inbox: "queue.Queue[Frame]"):
        self.sock = socket.create_connection((host, port))
        self.inbox = inbox
        self._parser = PacketStreamParser()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        while True:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            for frame in self._parser.feed(chunk):
                self.inbox.put(frame)

    def send(self, cmd: str, val=None) -> None:
        self.sock.sendall(encode(cmd, val))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class ConsoleApp(tk.Tk):
    def __init__(self, host: str, port: int):
        super().__init__()
        self.title("X-ray Source Console (simulator)")
        self.geometry("820x760")

        self.inbox: "queue.Queue[Frame]" = queue.Queue()
        self.link = SimulatorLink(host, port, self.inbox)
        self._suppress_send = False  # avoid re-sending while applying an echoed STATE update

        self.capture_history: list[CaptureRecord] = []
        self._drag_start = None  # (x_root, y_root) recorded on ButtonPress-1

        self._build_widgets()
        self.link.send(Command.SYNC_STATE)
        self.after(50, self._poll_inbox)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- UI construction -------------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        self.exposure_var = tk.StringVar(value="OFF")
        self.exposure_label = tk.Label(top, textvariable=self.exposure_var, fg="white",
                                        bg=EXPOSURE_COLORS["OFF"], width=12, font=("Segoe UI", 11, "bold"))
        self.exposure_label.pack(side="left")
        self.tube_temp_var = tk.StringVar(value="Tube temp: 0.0")
        ttk.Label(top, textvariable=self.tube_temp_var).pack(side="left", padx=16)

        form = ttk.Frame(self)
        form.pack(fill="x", **pad)

        self.kvp_var = tk.IntVar(value=70)
        self._slider_row(form, 0, "kVp", self.kvp_var, 40, 150, Command.SET_KVP)

        self.ma_var = tk.IntVar(value=10)
        self._slider_row(form, 1, "mA", self.ma_var, 1, 500, Command.SET_MA)

        self.brightness_var = tk.IntVar(value=50)
        self._slider_row(form, 2, "Brightness", self.brightness_var, 0, 100, Command.SET_BRIGHTNESS)

        self.contrast_var = tk.IntVar(value=50)
        self._slider_row(form, 3, "Contrast", self.contrast_var, 0, 100, Command.SET_CONTRAST)

        mode_row = ttk.Frame(self)
        mode_row.pack(fill="x", **pad)
        ttk.Label(mode_row, text="Mode", width=12).pack(side="left")
        self.mode_var = tk.StringVar(value="FLUORO")
        mode_box = ttk.Combobox(mode_row, textvariable=self.mode_var, values=MODES, state="readonly")
        mode_box.pack(side="left")
        mode_box.bind("<<ComboboxSelected>>", lambda e: self.link.send(Command.SET_MODE, self.mode_var.get()))

        zoom_row = ttk.Frame(self)
        zoom_row.pack(fill="x", **pad)
        ttk.Label(zoom_row, text="Zoom", width=12).pack(side="left")
        for label, val in (("x1", 0), ("x1.5", 1), ("x2", 2)):
            ttk.Button(zoom_row, text=label, command=lambda v=val: self.link.send(Command.SET_ZOOM, v)).pack(side="left", padx=2)

        self.flip_h_var = tk.BooleanVar(value=False)
        self.flip_v_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(zoom_row, text="Flip H", variable=self.flip_h_var,
                         command=lambda: self.link.send(Command.FLIP_H, self.flip_h_var.get())).pack(side="left", padx=12)
        ttk.Checkbutton(zoom_row, text="Flip V", variable=self.flip_v_var,
                         command=lambda: self.link.send(Command.FLIP_V, self.flip_v_var.get())).pack(side="left")

        ttk.Button(self, text="CAPTURE", command=self._on_capture).pack(fill="x", padx=8, pady=8)

        self._build_compare_panels()
        self._build_filmstrip()

        self.log_text = tk.Text(self, height=6, state="disabled", bg="#111", fg="#0f0", font=("Consolas", 9))
        self.log_text.pack(fill="x", padx=8, pady=(0, 8))

    def _build_compare_panels(self) -> None:
        compare = ttk.Frame(self)
        compare.pack(fill="x", padx=8, pady=4)

        left = ttk.Frame(compare)
        left.pack(side="left", expand=True, fill="both", padx=(0, 4))
        ttk.Label(left, text="Console capture (PNG)").pack(anchor="w")
        self.compare_left_label = tk.Label(left, bg="#222", fg="#888", height=14,
                                            text="(no capture yet)")
        self.compare_left_label.pack(fill="both", expand=True)

        right = ttk.Frame(compare)
        right.pack(side="left", expand=True, fill="both", padx=(4, 0))
        ttk.Label(right, text="DICOM round-trip (decoded from .dcm)").pack(anchor="w")
        self.compare_right_label = tk.Label(right, bg="#222", fg="#888", height=14,
                                             text="(no capture yet)")
        self.compare_right_label.pack(fill="both", expand=True)

        self._compare_left_photo = None
        self._compare_right_photo = None
        self.selected_index_var = tk.StringVar(value="Selected: none")
        ttk.Label(self, textvariable=self.selected_index_var).pack(anchor="w", padx=8)

    def _build_filmstrip(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="x", padx=8, pady=4)
        ttk.Label(outer, text="Capture history (drag to pan, click to select)").pack(anchor="w")

        self.filmstrip_canvas = tk.Canvas(outer, height=110, bg="#1a1a1a", highlightthickness=0)
        self.filmstrip_canvas.pack(fill="x")
        hbar = ttk.Scrollbar(outer, orient="horizontal", command=self.filmstrip_canvas.xview)
        hbar.pack(fill="x")
        self.filmstrip_canvas.configure(xscrollcommand=hbar.set)

        self.filmstrip_inner = tk.Frame(self.filmstrip_canvas, bg="#1a1a1a")
        self.filmstrip_canvas.create_window((0, 0), window=self.filmstrip_inner, anchor="nw")
        self.filmstrip_inner.bind(
            "<Configure>",
            lambda e: self.filmstrip_canvas.configure(scrollregion=self.filmstrip_canvas.bbox("all")),
        )

        # Click-and-drag panning (Tk's scan_mark/scan_dragto idiom).
        self.filmstrip_canvas.bind("<ButtonPress-1>", self._pan_press)
        self.filmstrip_canvas.bind("<B1-Motion>", self._pan_drag)
        # Mouse wheel also scrolls the strip horizontally.
        self.filmstrip_canvas.bind("<MouseWheel>", lambda e: self.filmstrip_canvas.xview_scroll(-1 * (e.delta // 120), "units"))

    def _slider_row(self, parent, row, label, var, lo, hi, cmd):
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky="w")
        scale = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                           command=lambda v: None)  # live drag doesn't spam the socket
        scale.grid(row=row, column=1, sticky="ew", padx=6)
        parent.columnconfigure(1, weight=1)
        value_label = ttk.Label(parent, textvariable=var, width=5)
        value_label.grid(row=row, column=2)
        scale.bind("<ButtonRelease-1>", lambda e, c=cmd, v=var: self._send_if_not_suppressed(c, int(v.get())))

    def _send_if_not_suppressed(self, cmd, val) -> None:
        if not self._suppress_send:
            self.link.send(cmd, val)

    # ---- filmstrip drag-to-pan ---------------------------------------------

    def _pan_press(self, event) -> None:
        self.filmstrip_canvas.scan_mark(event.x_root, event.y_root)
        self._drag_start = (event.x_root, event.y_root)

    def _pan_drag(self, event) -> None:
        self.filmstrip_canvas.scan_dragto(event.x_root, event.y_root, gain=1)

    def _thumb_press(self, event) -> None:
        self.filmstrip_canvas.scan_mark(event.x_root, event.y_root)
        self._drag_start = (event.x_root, event.y_root)

    def _thumb_drag(self, event) -> None:
        self.filmstrip_canvas.scan_dragto(event.x_root, event.y_root, gain=1)

    def _thumb_release(self, event, record: CaptureRecord) -> None:
        if self._drag_start is None:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        if abs(dx) < DRAG_CLICK_THRESHOLD and abs(dy) < DRAG_CLICK_THRESHOLD:
            self._select_capture(record)
        self._drag_start = None

    # ---- event handlers ---------------------------------------------------

    def _on_capture(self) -> None:
        self.link.send(Command.CAPTURE)

    def _on_close(self) -> None:
        self.link.close()
        self.destroy()

    # ---- inbound frame handling --------------------------------------------

    def _poll_inbox(self) -> None:
        try:
            while True:
                frame = self.inbox.get_nowait()
                self._apply_frame(frame)
        except queue.Empty:
            pass
        self.after(50, self._poll_inbox)

    def _apply_frame(self, frame: Frame) -> None:
        self._log(f"<- {frame.cmd} {frame.val}")
        self._suppress_send = True
        try:
            if frame.cmd == Command.STATE:
                field, value = frame.val["field"], frame.val["value"]
                if field == "kvp":
                    self.kvp_var.set(value)
                elif field == "ma":
                    self.ma_var.set(value)
                elif field == "mode":
                    self.mode_var.set(value)
                elif field == "brightness":
                    self.brightness_var.set(value)
                elif field == "contrast":
                    self.contrast_var.set(value)
                elif field == "flip_h":
                    self.flip_h_var.set(value)
                elif field == "flip_v":
                    self.flip_v_var.set(value)
            elif frame.cmd == Command.EXPOSURE_STATE:
                self.exposure_var.set(frame.val)
                self.exposure_label.config(bg=EXPOSURE_COLORS.get(frame.val, "#666666"))
            elif frame.cmd == Command.TUBE_TEMP:
                self.tube_temp_var.set(f"Tube temp: {frame.val:.1f}")
            elif frame.cmd == Command.CAPTURE_DONE:
                self._on_capture_done(frame.val)
        finally:
            self._suppress_send = False

    # ---- capture history / compare / filmstrip -----------------------------

    def _on_capture_done(self, payload) -> None:
        if not isinstance(payload, dict) or "path" not in payload:
            self._log(f"   capture failed: {payload}")
            return

        record = CaptureRecord(
            index=len(self.capture_history),
            png_path=payload["path"],
            dicom_path=payload.get("dicom_path", ""),
            dose_factor=payload.get("dose_factor", 0.0),
        )
        self.capture_history.append(record)
        self._add_thumbnail(record)
        self._select_capture(record)

    def _add_thumbnail(self, record: CaptureRecord) -> None:
        try:
            from PIL import Image, ImageTk
            img = Image.open(record.png_path)
            img.thumbnail(THUMB_SIZE)
            record.thumb_photo = ImageTk.PhotoImage(img)
        except Exception as exc:  # pragma: no cover - display-only best effort
            self._log(f"   thumbnail failed: {exc}")
            return

        lbl = tk.Label(self.filmstrip_inner, image=record.thumb_photo, bg="#1a1a1a",
                        bd=2, relief="flat", highlightthickness=1, highlightbackground="#1a1a1a")
        lbl.pack(side="left", padx=4, pady=4)
        lbl.bind("<ButtonPress-1>", self._thumb_press)
        lbl.bind("<B1-Motion>", self._thumb_drag)
        lbl.bind("<ButtonRelease-1>", lambda e, r=record: self._thumb_release(e, r))
        record.widget = lbl

        # keep the newest thumbnail in view
        self.filmstrip_canvas.update_idletasks()
        self.filmstrip_canvas.xview_moveto(1.0)

    def _select_capture(self, record: CaptureRecord) -> None:
        for r in self.capture_history:
            if r.widget is not None:
                r.widget.config(highlightbackground="#1a1a1a")
        if record.widget is not None:
            record.widget.config(highlightbackground="#4aa3ff")

        self.selected_index_var.set(
            f"Selected: capture #{record.index} (dose_factor={record.dose_factor:.3f})"
        )

        try:
            from PIL import ImageTk
            left_img = load_capture_preview(record.png_path)
            left_img.thumbnail(COMPARE_SIZE)
            self._compare_left_photo = ImageTk.PhotoImage(left_img)
            self.compare_left_label.config(image=self._compare_left_photo, text="")
        except Exception as exc:
            self.compare_left_label.config(image="", text=f"(preview failed: {exc})")

        try:
            from PIL import ImageTk
            right_img = load_dicom_preview(record.dicom_path)
            right_img.thumbnail(COMPARE_SIZE)
            self._compare_right_photo = ImageTk.PhotoImage(right_img)
            self.compare_right_label.config(image=self._compare_right_photo, text="")
        except Exception as exc:
            self.compare_right_label.config(image="", text=f"(decode failed: {exc})")

    def _log(self, line: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5588)
    args = ap.parse_args()
    app = ConsoleApp(args.host, args.port)
    app.mainloop()


if __name__ == "__main__":
    main()
