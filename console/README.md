# Console App

A from-scratch Tkinter desktop console for driving `../simulator/source_simulator.py`.
No layout, icon, or screenshot from any real product is used — see
[`../pipeline/PLAN.md`](../pipeline/PLAN.md) section 3-1.

## Quick start

```bash
python ../simulator/source_simulator.py --port 5588   # terminal 1
python console_app.py --port 5588                     # terminal 2
```

## What it does

- Connects over the shared `common.protocol` TCP link and requests a full
  state sync on startup.
- kVp / mA / brightness / contrast sliders send `SET_*` on release (not on
  every drag tick, to avoid flooding the socket).
- Mode dropdown, zoom buttons, flip checkboxes.
- CAPTURE button triggers an exposure; the resulting synthetic image is
  shown inline once `CAPTURE_DONE` arrives.
- A live log pane shows every frame sent/received, for debugging the
  protocol itself.
- All inbound state updates are applied through a queue drained on the Tk
  main loop (`after`), since Tkinter widgets aren't thread-safe and the
  socket reader runs on a background thread.

Verified against the simulator directly (state sync, mode/kVp/mA/APR
setting, capture round-trip) via a scripted TCP client — see the
simulator's own test in `../simulator/README.md`.
