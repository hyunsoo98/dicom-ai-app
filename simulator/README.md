# X-ray Source Simulator

Standalone TCP simulator for a virtual X-ray source, used to develop and
demo the rest of this project (console app, denoising inference, DICOM
export) without physical hardware.

**Original protocol.** The wire protocol (`protocol.py`), state/clamp rules
(`state.py`), and simulated hardware model here are all designed from
scratch for this project. Nothing here is reverse-engineered from, or
copied out of, any vendor's product — see [`../pipeline/PLAN.md`](../pipeline/PLAN.md)
section 3-1.

## Files

| File | Purpose |
|---|---|
| `../common/protocol.py` | Newline-delimited JSON frame encode/decode + stream parser (shared with `console/`) |
| `state.py` | `XraySourceState`: kVp/mA/mode/APR state and clamp rules |
| `noise_model.py` | Synthetic chest-phantom image + dose-dependent Poisson/Gaussian noise |
| `source_simulator.py` | TCP server: one `XraySourceSession` per connection, command dispatch, capture simulation |
| `dicom_export.py` | Packages a capture as a standard DICOM DX dataset and sends it via C-STORE |
| `console_client.py` | Interactive CLI for manually driving the simulator (see also `../console/console_app.py` for a GUI) |

## Quick start

```bash
# terminal 1 — the simulated X-ray source
python source_simulator.py --port 5588

# terminal 2 — interactive console
python console_client.py --port 5588
> sync
> mode radiography
> kvp 90
> ma 40
> capture
> quit
```

`capture` triggers a simulated exposure: the source transitions
`OFF -> EXPOSING -> OFF`, generates a synthetic noisy image whose noise
level depends on the current kVp/mA (via `state.relative_dose_factor()`),
saves it under `captures/`, and reports the path in `CAPTURE_DONE`.

### Sending captures to a DICOM viewer

```bash
pip install -r requirements.txt
python source_simulator.py --port 5588 --dicom-export
```

Every `CAPTURE` also sends the image as a standard DICOM DX dataset via
C-STORE to `--dicom-host`/`--dicom-port` (default `127.0.0.1:11114`, which
matches the sibling `dicom-xray-viewer` project's device-bridge listener).
Verified end-to-end against a standalone test SCP (Modality/Rows/Columns/
KVP/mA/BodyPart all arrive correctly); see `dicom_export.py`.

Denoising inference is not wired in yet — that lands once the model in
`pipeline/` exists (see `pipeline/PLAN.md` step 8), and would run on the
captured pixels before export.

## Wire protocol

One JSON object per line, UTF-8, newline-terminated:

```
{"cmd": "SET_KVP", "val": 90}\n
```

See `protocol.py` (`Command` class) for the full command list and
`state.py` for value ranges and clamp behavior.
