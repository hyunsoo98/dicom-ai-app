# Android Tablet Console — Design Plan

Replaces the Tkinter prototype (`../console/console_app.py`) with a real
Android Kotlin tablet app, so the actual operating console runs on a
tablet while the existing PC viewer stays as-is.

```
[Android Kotlin tablet console] --TCP (common/protocol.py wire format)--> [Python simulator] --DICOM C-STORE--> [PC WPF viewer: dicom-xray-viewer]
```

**Not built or build-verified yet.** This dev environment has no
Java/Android SDK/Gradle installed, so this is a design document to build
against in Android Studio — see "Open questions" at the end.

## 1. Origin and rules

The module layout and a few architectural ideas below are patterned after
`touch5k-tablet-console`, a personal Android project this author built
earlier (Compose + MVVM + a hardware-link interface abstracted behind a
`Fake` implementation for testing). Per [`../pipeline/PLAN.md`](../pipeline/PLAN.md)
section 3-1, this project reuses only that general architecture *shape* —
nothing else carries over:

- No `com.gemss.*` package names, class names, or file names
- No copied UI assets/icons/screenshots from any real product
- No reused protocol commands, codes, or clamp values — this app speaks
  the JSON-line protocol already defined in `../common/protocol.py`,
  reimplemented in Kotlin from that spec, not from any decompiled source
- No mention of the reference project's name anywhere in code or docs

Package root: `com.hs980.xraysim.console`.

## 2. Module layout

```
android-console/
├── app/                            entry point, screens, DI wiring
│   └── ...MainActivity.kt, ConsoleScreen.kt, ConsoleViewModel.kt
├── core/
│   ├── design-system/              Compose theme, colors, typography, shared widgets
│   │   └── XraySimColors.kt, XraySimTheme.kt, XraySimTypography.kt,
│   │       ConnectionBadge.kt, ConsoleActionButton.kt
│   └── source-link/                the hardware-link abstraction
│       ├── XraySourceLink.kt       interface: connect/disconnect, send(cmd,val), state Flow
│       ├── TcpXraySourceLink.kt    real implementation (Kotlin coroutines + Sockets)
│       ├── FakeXraySourceLink.kt   in-memory fake for Compose previews and unit tests
│       ├── Protocol.kt             Frame/Command/encode/parse - Kotlin port of common/protocol.py
│       └── SourceState.kt          client-side mirror of state.py's fields (for display)
└── settings.gradle.kts, build.gradle.kts
```

This mirrors `touch5k-tablet-console`'s `app` / `core/design-system` /
`core/carm-link` split — the same *reason* applies here: the app layer
never talks sockets directly, it only depends on the `XraySourceLink`
interface, so Compose previews and unit tests can run against
`FakeXraySourceLink` without a real simulator running.

## 3. Protocol port (`Protocol.kt`)

Direct Kotlin translation of `common/protocol.py` — newline-delimited
JSON, one object per line:

```kotlin
data class Frame(val cmd: String, val value: Any?)

object Command {
    const val SYNC_STATE = "SYNC_STATE"
    const val SET_KVP = "SET_KVP"
    const val SET_MA = "SET_MA"
    const val SET_MODE = "SET_MODE"
    const val SET_APR = "SET_APR"
    const val SET_BRIGHTNESS = "SET_BRIGHTNESS"
    const val SET_CONTRAST = "SET_CONTRAST"
    const val SET_ZOOM = "SET_ZOOM"
    const val FLIP_H = "FLIP_H"
    const val FLIP_V = "FLIP_V"
    const val CAPTURE = "CAPTURE"
    const val HEARTBEAT = "HEARTBEAT"
    const val STATE = "STATE"
    const val EXPOSURE_STATE = "EXPOSURE_STATE"
    const val TUBE_TEMP = "TUBE_TEMP"
    const val CAPTURE_DONE = "CAPTURE_DONE"
}
```

`encode(cmd, value)` serializes with `kotlinx.serialization` (or org.json,
TBD in "Open questions") to `{"cmd":"...","val":...}\n`. A
`FrameStreamParser` buffers partial reads the same way
`PacketStreamParser` does in Python — split on `\n`, keep the remainder.

**Cross-language consistency check (to do once buildable):** run the
Python simulator and this Kotlin client against each other and confirm a
captured wire log matches what `common/protocol.py` produces/expects
byte-for-byte, the same way `verify_onnx.py` in the sibling project
compares against the real pipeline rather than a same-language wrapper.

## 4. `XraySourceLink` interface

```kotlin
interface XraySourceLink {
    val state: StateFlow<SourceUiState>
    suspend fun connect(host: String, port: Int)
    fun send(cmd: String, value: Any? = null)
    fun disconnect()
}
```

- `TcpXraySourceLink`: opens a `Socket`, a coroutine reads lines and folds
  incoming `STATE`/`EXPOSURE_STATE`/`TUBE_TEMP`/`CAPTURE_DONE` frames into
  `SourceUiState`, exposed as a `StateFlow` the Compose screen collects.
- `FakeXraySourceLink`: holds an in-memory `SourceUiState`, `send()`
  mutates it directly with the same clamp rules as `state.py` (ported to
  Kotlin) so Compose previews and instrumented tests behave like the real
  simulator without a socket.

## 5. Screen

Single `ConsoleScreen` (no multi-tab Fluoro/Radiography/Setting split like
the reference project — this app's scope is simpler: one control surface).

- Connection badge (reusing the visual *idea* of the reference project's
  `ConnectionBadge`, redrawn from scratch) showing OFF/READY/EXPOSING with
  color, plus tube temp
- Sliders: kVp, mA, brightness, contrast (send `SET_*` on release, not on
  every drag tick — same reasoning as the Tkinter prototype)
- Mode dropdown, zoom buttons, flip toggles
- CAPTURE button
- No local image preview/compare/filmstrip on the tablet itself — that
  stays the PC viewer's job (per the corrected architecture: tablet
  drives exposure, PC views the result). If a "just captured" thumbnail
  turns out to be worth having on the tablet too, it's a later addition,
  not in this first pass.

`ConsoleViewModel` wraps a `XraySourceLink` (injected — `Tcp` in
production, `Fake` in previews/tests) and exposes UI state.

## 6. Testing plan (once buildable)

- Unit tests: `Protocol.kt` encode/parse round-trip; `SourceState` clamp
  logic port, mirroring `simulator/state.py`'s behavior for the same
  inputs (kVp/mA ranges, mode-dependent mA ceiling)
- `FakeXraySourceLink`-backed Compose UI tests for slider -> state update
- Manual integration test: real tablet (or emulator) against
  `python simulator/source_simulator.py`, same scenario as the Python
  console's verified test (state sync, mode/kVp/mA/APR set, capture)

## 7. Open questions

1. JSON library: `kotlinx.serialization` (needs a Gradle plugin) vs. plain
   `org.json` (built into Android, no extra dependency, less type-safe).
   Leaning `org.json` for a small protocol like this — decide once
   actually wiring it up.
2. Minimum SDK / Compose BOM version — pick to match whatever tablet this
   gets tested on.
3. Whether to keep the Tkinter console (`../console/`) around afterward
   as a quick desktop-side testing tool for the simulator, independent of
   the tablet app — likely yes, it's still useful for fast iteration
   without a device.
