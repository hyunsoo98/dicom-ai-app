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
- CAPTURE button triggers an exposure.
- **Compare panels**: every capture shows two images side by side —
  the console's own PNG preview, and the same capture *decoded back from
  the actual `.dcm` file* the simulator built (see
  `simulator/source_simulator.py` — it now always saves a DICOM object
  locally, independent of whether `--dicom-export` also sends it to a
  live viewer). This is a real round-trip check, not just the same array
  shown twice: `common/imaging.load_dicom_preview` reads `PixelData` back
  out of the file. Verified byte-exact in a standalone script (see commit
  history) before wiring it into the UI.
- **Filmstrip**: every capture this session gets a thumbnail in a
  horizontally scrollable strip below the compare panels. Click a
  thumbnail to load it into the compare panels; click-and-drag anywhere
  on the strip (including on a thumbnail) to pan, using Tk's
  `scan_mark`/`scan_dragto` idiom. A press+release under 5px of movement
  is treated as a click rather than a drag.
- A live log pane shows every frame sent/received, for debugging the
  protocol itself.
- All inbound state updates are applied through a queue drained on the Tk
  main loop (`after`), since Tkinter widgets aren't thread-safe and the
  socket reader runs on a background thread.

## Verification notes

The protocol-level flow (state sync, mode/kVp/mA/APR setting, capture
round-trip, PNG+DICOM both landing on disk) is verified via scripted TCP
clients — see `../simulator/README.md`. The DICOM decode used by the
right-hand compare panel was separately verified to be pixel-exact against
the source array. The Tkinter-specific pieces (thumbnail layout, drag-to-pan
feel) use standard, well-documented Tk idioms but haven't been
click-tested interactively in this environment — run the app yourself to
confirm the UI feels right.
