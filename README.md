# DICOM AI App

Personal project: an original X-ray source simulator + console, feeding
standard DICOM images into a real DICOM viewer, with an AI denoising model
(in progress) planned to sit in that pipeline. See
[`pipeline/PLAN.md`](pipeline/PLAN.md) for the full design and the rules
this project follows (in particular: no vendor-specific protocol, assets,
or naming from any real product anywhere in this repo).

> Learning/research project. Not for clinical use.

## Layout

| Path | What |
|---|---|
| [`common/`](common) | Shared protocol (`protocol.py`) and pixel/preview conversion (`imaging.py`) used by both `simulator/` and `console/` |
| [`simulator/`](simulator) | TCP server simulating an X-ray source: state machine, dose-dependent noise synthesis, DICOM export | 
| [`console/`](console) | Tkinter desktop console: drives the simulator, compare view (PNG vs DICOM round-trip), capture filmstrip |
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
- [ ] Denoising model training pipeline
- [ ] ONNX conversion + verification
- [ ] TensorRT benchmark (blocked on access to an NVIDIA GPU - this
      machine only has integrated graphics; see `pipeline/PLAN.md`)
- [ ] Wire the trained model into the simulator/viewer pipeline
