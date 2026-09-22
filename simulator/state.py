"""State machine for the simulated X-ray source.

All ranges, clamp rules, and the tube-heat model below are original
approximations invented for this project (loosely inspired by how real
generators behave in general: higher exposure -> more tube heat, low-dose
modes cap current). They are not copied from, or reverse-engineered from,
any specific vendor's equipment or documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KVP_MIN, KVP_MAX = 40, 150
MA_MIN, MA_MAX = 1, 500

EXPOSURE_MODES = ("FLUORO", "RADIOGRAPHY", "PULSED", "LOW_DOSE")

# mA ceiling per mode - a simplified, self-defined tube-protection rule:
# continuous fluoroscopy runs at much lower current than a single snapshot.
MODE_MA_CEILING = {
    "FLUORO": 10,
    "PULSED": 50,
    "LOW_DOSE": 100,
    "RADIOGRAPHY": MA_MAX,
}

APR_REGIONS = ("NONE", "CHEST", "ABDOMEN", "EXTREMITY", "SPINE")
APR_SIZES = ("SMALL", "MEDIUM", "LARGE")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class XraySourceState:
    kvp: int = 70
    ma: int = 10
    mode: str = "FLUORO"
    apr_region: str = "NONE"
    apr_size: str = "MEDIUM"
    brightness: int = 50
    contrast: int = 50
    zoom: int = 0
    flip_h: bool = False
    flip_v: bool = False
    exposure_state: str = "OFF"  # OFF | READY | EXPOSING
    tube_temp: float = 0.0
    log: list[str] = field(default_factory=list)

    def set_kvp(self, value: int) -> int:
        self.kvp = int(clamp(value, KVP_MIN, KVP_MAX))
        return self.kvp

    def set_mode(self, mode: str) -> str:
        if mode not in EXPOSURE_MODES:
            mode = "FLUORO"
        self.mode = mode
        # re-clamp current mA against the new mode's ceiling
        self.ma = int(clamp(self.ma, MA_MIN, MODE_MA_CEILING[mode]))
        return self.mode

    def set_ma(self, value: int) -> int:
        ceiling = MODE_MA_CEILING[self.mode]
        self.ma = int(clamp(value, MA_MIN, ceiling))
        return self.ma

    def set_apr(self, region: str, size: str) -> tuple[str, str]:
        self.apr_region = region if region in APR_REGIONS else "NONE"
        self.apr_size = size if size in APR_SIZES else "MEDIUM"
        return self.apr_region, self.apr_size

    def set_brightness(self, value: int) -> int:
        self.brightness = int(clamp(value, 0, 100))
        return self.brightness

    def set_contrast(self, value: int) -> int:
        self.contrast = int(clamp(value, 0, 100))
        return self.contrast

    def set_zoom(self, value: int) -> int:
        self.zoom = int(clamp(value, 0, 2))
        return self.zoom

    def relative_dose_factor(self) -> float:
        """A single 0-1 "how much signal did the detector see" estimate,
        derived from kVp and mA. Used by the noise model to decide how
        noisy a captured image should look — lower dose -> more quantum
        noise. This is a simplified proportionality, not a physical model.
        """
        kvp_frac = (self.kvp - KVP_MIN) / (KVP_MAX - KVP_MIN)
        ma_frac = self.ma / MA_MAX
        return clamp(0.15 + 0.85 * (0.4 * kvp_frac + 0.6 * ma_frac), 0.02, 1.0)

    def accumulate_heat(self) -> float:
        """Self-defined heat model: heat added per exposure scales with
        mA and is higher for continuous modes (fluoro/pulsed) than a
        single radiography shot.
        """
        mode_factor = 1.5 if self.mode in ("FLUORO", "PULSED") else 1.0
        added = mode_factor * (self.ma / MA_MAX) * 8.0
        self.tube_temp = clamp(self.tube_temp + added, 0.0, 100.0)
        return self.tube_temp

    def cool_down(self, amount: float = 2.0) -> float:
        self.tube_temp = clamp(self.tube_temp - amount, 0.0, 100.0)
        return self.tube_temp
