"""Simulated X-ray source (generator) for the DICOM AI App project.

Standalone TCP server that plays the role of an X-ray source's control MCU
so the rest of the pipeline (console app, denoising inference, DICOM export)
can be developed and demoed without physical hardware.

The wire protocol (`protocol.py`) and the state/clamp rules (`state.py`)
are original designs written for this project - see pipeline/PLAN.md
section 3-1 for why: no vendor spec, decompiled app, or reverse-engineered
protocol is used anywhere in this repository.

Usage:
    python source_simulator.py [--port 5588]

Then connect with console_client.py (or your own tool) to the same port.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import noise_model
import state as state_mod
from common.protocol import Command, Frame, PacketStreamParser, encode

CAPTURE_OUTPUT_DIR = Path(__file__).parent / "captures"
IMAGE_WIDTH, IMAGE_HEIGHT = 512, 512


def _save_capture_png(pixels, path: Path) -> None:
    from PIL import Image

    # 12-bit -> 8-bit just for a quick-look PNG; the DICOM export step
    # (added later) will carry the full-precision pixel data instead.
    img8 = (pixels.astype("float32") / 4095.0 * 255.0).clip(0, 255).astype("uint8")
    Image.fromarray(img8, mode="L").save(path)


class XraySourceSession:
    """One connected console's view of the simulated source."""

    def __init__(self, sock: socket.socket, addr, verbose: bool = True,
                 dicom_export: bool = False, dicom_host: str = "127.0.0.1", dicom_port: int = 11114):
        self.sock = sock
        self.addr = addr
        self.verbose = verbose
        self.state = state_mod.XraySourceState()
        self.parser = PacketStreamParser()
        self._lock = threading.Lock()
        self.dicom_export = dicom_export
        self.dicom_host = dicom_host
        self.dicom_port = dicom_port

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{self.addr[0]}:{self.addr[1]}] {msg}")

    def send(self, cmd: str, val=None) -> None:
        with self._lock:
            self.sock.sendall(encode(cmd, val))
        self.log(f"-> {cmd}={val}")

    def handle_frame(self, frame: Frame) -> None:
        self.log(f"<- {frame.cmd}={frame.val}")
        handler = DISPATCH.get(frame.cmd)
        if handler is None:
            self.log(f"   (no handler for {frame.cmd}, ignoring)")
            return
        handler(self, frame.val)

    def sync_state(self, _val=None) -> None:
        s = self.state
        self.send(Command.STATE, {"field": "kvp", "value": s.kvp})
        self.send(Command.STATE, {"field": "ma", "value": s.ma})
        self.send(Command.STATE, {"field": "mode", "value": s.mode})
        self.send(Command.STATE, {"field": "apr", "value": [s.apr_region, s.apr_size]})
        self.send(Command.STATE, {"field": "brightness", "value": s.brightness})
        self.send(Command.STATE, {"field": "contrast", "value": s.contrast})
        self.send(Command.STATE, {"field": "zoom", "value": s.zoom})
        self.send(Command.EXPOSURE_STATE, s.exposure_state)
        self.send(Command.TUBE_TEMP, s.tube_temp)

    def do_capture(self, _val=None) -> None:
        threading.Thread(target=self._simulate_exposure, daemon=True).start()

    def _simulate_exposure(self) -> None:
        s = self.state
        s.exposure_state = "EXPOSING"
        self.send(Command.EXPOSURE_STATE, s.exposure_state)
        time.sleep(0.3)

        dose_factor = s.relative_dose_factor()
        pixels = noise_model.synthesize_capture(IMAGE_WIDTH, IMAGE_HEIGHT, dose_factor)

        CAPTURE_OUTPUT_DIR.mkdir(exist_ok=True)
        out_path = CAPTURE_OUTPUT_DIR / f"capture_{uuid.uuid4().hex[:8]}.png"
        _save_capture_png(pixels, out_path)

        s.accumulate_heat()
        s.exposure_state = "OFF"
        self.send(Command.EXPOSURE_STATE, s.exposure_state)
        self.send(Command.TUBE_TEMP, s.tube_temp)
        self.send(Command.CAPTURE_DONE, {"path": str(out_path), "dose_factor": dose_factor})

        if self.dicom_export:
            self._export_dicom(pixels)
        # Denoising inference is wired in here once the pipeline/denoise
        # model exists (see pipeline/PLAN.md step 8) - it would run on
        # `pixels` before export, alongside or instead of the raw capture.

    def _export_dicom(self, pixels) -> None:
        try:
            import dicom_export
        except ImportError as exc:
            self.log(f"   (DICOM export skipped: {exc})")
            return
        ds = dicom_export.build_dataset(self.state, pixels)
        ok, message = dicom_export.send_to_viewer(ds, host=self.dicom_host, port=self.dicom_port)
        self.log(f"   DICOM export {'OK' if ok else 'FAILED'}: {message}")

    def run(self) -> None:
        self.log("connected")
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                for frame in self.parser.feed(chunk):
                    self.handle_frame(frame)
        except (ConnectionResetError, OSError):
            pass
        finally:
            self.log("disconnected")
            self.sock.close()


def _set_kvp(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "kvp", "value": session.state.set_kvp(int(val))})


def _set_ma(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "ma", "value": session.state.set_ma(int(val))})


def _set_mode(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "mode", "value": session.state.set_mode(str(val))})


def _set_apr(session: XraySourceSession, val) -> None:
    region, size = val.get("region", "NONE"), val.get("size", "MEDIUM")
    r, sz = session.state.set_apr(region, size)
    session.send(Command.STATE, {"field": "apr", "value": [r, sz]})


def _set_brightness(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "brightness", "value": session.state.set_brightness(int(val))})


def _set_contrast(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "contrast", "value": session.state.set_contrast(int(val))})


def _set_zoom(session: XraySourceSession, val) -> None:
    session.send(Command.STATE, {"field": "zoom", "value": session.state.set_zoom(int(val))})


def _set_flip_h(session: XraySourceSession, val) -> None:
    session.state.flip_h = bool(val)
    session.send(Command.STATE, {"field": "flip_h", "value": session.state.flip_h})


def _set_flip_v(session: XraySourceSession, val) -> None:
    session.state.flip_v = bool(val)
    session.send(Command.STATE, {"field": "flip_v", "value": session.state.flip_v})


def _heartbeat(session: XraySourceSession, _val) -> None:
    session.send(Command.HEARTBEAT, "ok")


DISPATCH = {
    Command.SYNC_STATE: XraySourceSession.sync_state,
    Command.SET_KVP: _set_kvp,
    Command.SET_MA: _set_ma,
    Command.SET_MODE: _set_mode,
    Command.SET_APR: _set_apr,
    Command.SET_BRIGHTNESS: _set_brightness,
    Command.SET_CONTRAST: _set_contrast,
    Command.SET_ZOOM: _set_zoom,
    Command.FLIP_H: _set_flip_h,
    Command.FLIP_V: _set_flip_v,
    Command.CAPTURE: XraySourceSession.do_capture,
    Command.HEARTBEAT: _heartbeat,
}


def serve(host: str, port: int, *, dicom_export: bool = False,
          dicom_host: str = "127.0.0.1", dicom_port: int = 11114) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen()
        print(f"X-ray source simulator listening on {host}:{port}")
        if dicom_export:
            print(f"DICOM export on CAPTURE -> {dicom_host}:{dicom_port}")
        while True:
            conn, addr = server.accept()
            session = XraySourceSession(conn, addr, dicom_export=dicom_export,
                                         dicom_host=dicom_host, dicom_port=dicom_port)
            threading.Thread(target=session.run, daemon=True).start()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5588)
    ap.add_argument("--dicom-export", action="store_true",
                     help="on CAPTURE, also send the image to a DICOM receiver over C-STORE")
    ap.add_argument("--dicom-host", default="127.0.0.1")
    ap.add_argument("--dicom-port", type=int, default=11114,
                     help="matches DicomXrayViewer's device-bridge default port")
    args = ap.parse_args()
    try:
        serve(args.host, args.port, dicom_export=args.dicom_export,
              dicom_host=args.dicom_host, dicom_port=args.dicom_port)
    except KeyboardInterrupt:
        pass
