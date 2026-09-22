# DICOM AI App

Personal project simulating an X-ray source + operating console, feeding
standard DICOM images into a real PC DICOM viewer, with an AI denoising
model (in progress) planned to sit in that pipeline. See
[`pipeline/PLAN.md`](pipeline/PLAN.md) for the full design and the rules
this project follows (in particular: no vendor-specific protocol, assets,
or naming from any real product anywhere in this repo).

> Learning/research project. Not for clinical use.

## Architecture

```
[Android Kotlin tablet console] --TCP--> [Python source simulator] --DICOM C-STORE--> [PC viewer: dicom-xray-viewer]
```

The tablet console is the operator-facing app (kVp/mA/mode/capture); the
PC viewer displays/analyzes the resulting images. The two are separate
processes/devices on purpose, matching how a real X-ray room is laid out.

## Layout

| Path | What |
|---|---|
| [`common/`](common) | Shared protocol (`protocol.py`) and pixel/preview conversion (`imaging.py`) used by `simulator/` and `console/` |
| [`simulator/`](simulator) | TCP server simulating an X-ray source: state machine, dose-dependent noise synthesis, DICOM export |
| [`android-console/`](android-console) | **Planned** — the real operating console, an Android Kotlin tablet app (design doc only so far, not yet buildable in this dev environment; see its `PLAN.md`) |
| [`console/`](console) | Tkinter desktop console — a prototype/testing tool for driving the simulator from a PC without a tablet, kept around after `android-console/` exists too |
| [`pipeline/`](pipeline) | Project plan; the denoising model training/ONNX/TensorRT pipeline lands here |

## Quick start

```bash
pip install -r simulator/requirements.txt
pip install -r console/requirements.txt

python simulator/source_simulator.py --port 5588   # terminal 1
python console/console_app.py --port 5588          # terminal 2
```

Or with Docker (simulator only — the console needs a display so it runs
on the host):

```bash
docker compose up simulator
python console/console_app.py --port 5588
```

See `Makefile` for shortcuts (`make run-simulator`, `make run-console`,
`make docker-up`, `make test`).

## Sending captures to a DICOM viewer

```bash
python simulator/source_simulator.py --port 5588 --dicom-export
```

Every capture is C-STOREd to `127.0.0.1:11114` by default, matching the
device-bridge listener in the sibling
[`dicom-xray-viewer`](https://github.com/hyunsoo98/dicom-xray-viewer)
project. See `simulator/README.md` for details.

## Status

- [x] Original TCP protocol + state machine (`common/`, `simulator/state.py`)
- [x] Dose-dependent synthetic noise generation
- [x] Console app with live controls, compare view, capture filmstrip
- [x] Standard DICOM export (C-STORE), verified against a real DICOM receiver
- [x] Docker Compose + Makefile for the simulator
- [ ] Android tablet console (design doc written, `android-console/PLAN.md`;
      no Java/Android SDK/Gradle in this dev environment, so not yet
      buildable here — needs Android Studio)
- [ ] Denoising model training pipeline
- [ ] ONNX conversion + verification
- [ ] TensorRT benchmark (blocked on access to an NVIDIA GPU - this
      machine only has integrated graphics; see `pipeline/PLAN.md`)
- [ ] Wire the trained model into the simulator/viewer pipeline
