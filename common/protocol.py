"""Wire protocol for the X-ray source simulator link.

This is an original, from-scratch protocol design for this project. It is
newline-delimited JSON over a plain TCP socket: simple to parse, easy to log,
and easy to extend with new fields without breaking a fixed byte layout.

Frame shape (one JSON object per line, UTF-8, "\n"-terminated)::

    {"cmd": "SET_KVP", "val": 80}\n

- "cmd" (str): command name, see `Command`.
- "val" (int | float | str | None): payload, meaning depends on the command.
- A malformed line (bad JSON, missing "cmd") is dropped and logged; the
  stream resyncs on the next newline rather than tearing down the
  connection, mirroring how line-oriented protocols are expected to behave.

Both directions (console -> source, source -> console) use the same frame
shape. A "set" from the console and a "status" push from the source look
identical on the wire; only the command name and the direction of travel
differ.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator


class Command:
    """Command names understood by the source simulator and console."""

    # console -> source
    SYNC_STATE = "SYNC_STATE"          # request a full state dump
    SET_KVP = "SET_KVP"                # kVp setpoint
    SET_MA = "SET_MA"                  # mA setpoint
    SET_MODE = "SET_MODE"              # exposure mode, see ExposureMode
    SET_APR = "SET_APR"                # anatomical preset {"region": int, "size": int}
    SET_BRIGHTNESS = "SET_BRIGHTNESS"  # 0-100
    SET_CONTRAST = "SET_CONTRAST"      # 0-100
    SET_ZOOM = "SET_ZOOM"              # 0 = x1, 1 = x1.5, 2 = x2
    FLIP_H = "FLIP_H"                  # bool
    FLIP_V = "FLIP_V"                  # bool
    CAPTURE = "CAPTURE"                # trigger one exposure
    HEARTBEAT = "HEARTBEAT"            # keepalive

    # source -> console (status pushes / acks)
    STATE = "STATE"                    # one field of state, echoed after a SET_* or SYNC_STATE
    EXPOSURE_STATE = "EXPOSURE_STATE"  # "OFF" | "READY" | "EXPOSING"
    TUBE_TEMP = "TUBE_TEMP"            # 0-100, heat accumulation
    CAPTURE_DONE = "CAPTURE_DONE"      # {"path": str} or {"error": str}


ALL_COMMANDS = {
    v for k, v in vars(Command).items() if not k.startswith("_") and isinstance(v, str)
}


@dataclass(frozen=True)
class Frame:
    cmd: str
    val: Any = None

    def to_line(self) -> str:
        return json.dumps({"cmd": self.cmd, "val": self.val}, separators=(",", ":")) + "\n"


def encode(cmd: str, val: Any = None) -> bytes:
    return Frame(cmd, val).to_line().encode("utf-8")


class PacketStreamParser:
    """Buffers raw TCP bytes and yields complete `Frame`s.

    TCP gives no message boundaries, so a `recv()` may return a partial
    line, multiple lines, or a line split across two calls. This buffers
    everything and only yields once a full "\n"-terminated line is seen.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: bytes) -> Iterator[Frame]:
        self._buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            frame = self._parse_line(line)
            if frame is not None:
                yield frame

    @staticmethod
    def _parse_line(line: str) -> Frame | None:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict) or "cmd" not in obj:
            return None
        cmd = obj["cmd"]
        if not isinstance(cmd, str):
            return None
        return Frame(cmd=cmd, val=obj.get("val"))
