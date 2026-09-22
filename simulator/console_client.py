"""Minimal interactive CLI console for testing source_simulator.py.

Usage:
    python source_simulator.py --port 5588      # terminal 1
    python console_client.py --port 5588        # terminal 2
    > sync
    > kvp 90
    > ma 40
    > mode radiography
    > capture
    > quit
"""

from __future__ import annotations

import argparse
import socket
import threading

from protocol import Command, PacketStreamParser, encode


def _reader(sock: socket.socket) -> None:
    parser = PacketStreamParser()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            print("(disconnected)")
            break
        for frame in parser.feed(chunk):
            print(f"<- {frame.cmd}={frame.val}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5588)
    args = ap.parse_args()

    sock = socket.create_connection((args.host, args.port))
    threading.Thread(target=_reader, args=(sock,), daemon=True).start()

    print("Connected. Commands: sync, kvp <v>, ma <v>, mode <name>, "
          "brightness <v>, contrast <v>, zoom <v>, capture, heartbeat, quit")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        parts = line.split()
        cmd, args_ = parts[0].lower(), parts[1:]

        if cmd == "quit":
            break
        elif cmd == "sync":
            sock.sendall(encode(Command.SYNC_STATE))
        elif cmd == "kvp":
            sock.sendall(encode(Command.SET_KVP, int(args_[0])))
        elif cmd == "ma":
            sock.sendall(encode(Command.SET_MA, int(args_[0])))
        elif cmd == "mode":
            sock.sendall(encode(Command.SET_MODE, args_[0].upper()))
        elif cmd == "brightness":
            sock.sendall(encode(Command.SET_BRIGHTNESS, int(args_[0])))
        elif cmd == "contrast":
            sock.sendall(encode(Command.SET_CONTRAST, int(args_[0])))
        elif cmd == "zoom":
            sock.sendall(encode(Command.SET_ZOOM, int(args_[0])))
        elif cmd == "capture":
            sock.sendall(encode(Command.CAPTURE))
        elif cmd == "heartbeat":
            sock.sendall(encode(Command.HEARTBEAT))
        else:
            print(f"unknown command: {cmd}")

    sock.close()


if __name__ == "__main__":
    main()
