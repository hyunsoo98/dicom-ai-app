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
| `protocol.py` | Newline-delimited JSON frame encode/decode + stream parser |
| `state.py` | `XraySourceState`: kVp/mA/mode/APR state and clamp rules |
| `noise_model.py` | Synthetic chest-phantom image + dose-dependent Poisson/Gaussian noise |
| `source_simulator.py` | TCP server: one `XraySourceSession` per connection, command dispatch, capture simulation |
| `console_client.py` | Interactive CLI for manually driving the simulator |

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

Denoising inference and DICOM export are not wired in yet — that lands
once the model in `pipeline/` exists (see `pipeline/PLAN.md` step 8).

## Wire protocol

One JSON object per line, UTF-8, newline-terminated:

```
{"cmd": "SET_KVP", "val": 90}\n
```

See `protocol.py` (`Command` class) for the full command list and
`state.py` for value ranges and clamp behavior.
