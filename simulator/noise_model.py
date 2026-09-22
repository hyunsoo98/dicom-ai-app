"""Synthetic X-ray noise generation for the simulator.

Real X-ray detector noise is dominated by quantum (photon-counting) noise,
which is signal-dependent and well modeled as Poisson, plus a smaller
signal-independent Gaussian term from detector electronics. This module
uses that well-known general noise structure but is not derived from any
vendor's calibration data - the scale factors are picked to look plausible
for a demo, not to match a real detector.
"""

from __future__ import annotations

import numpy as np


def _phantom(width: int, height: int) -> np.ndarray:
    """A simple synthetic chest-like phantom: smooth field + a few soft
    structures, so denoising has something non-trivial to preserve.
    """
    yy, xx = np.mgrid[0:height, 0:width]
    cx, cy = width / 2, height / 2
    body = np.exp(-(((xx - cx) ** 2) / (2 * (width * 0.35) ** 2)
                     + ((yy - cy) ** 2) / (2 * (height * 0.45) ** 2)))
    lung_l = np.exp(-(((xx - cx + width * 0.18) ** 2) / (2 * (width * 0.12) ** 2)
                       + ((yy - cy) ** 2) / (2 * (height * 0.28) ** 2)))
    lung_r = np.exp(-(((xx - cx - width * 0.18) ** 2) / (2 * (width * 0.12) ** 2)
                       + ((yy - cy) ** 2) / (2 * (height * 0.28) ** 2)))
    field = 0.25 + 0.65 * body - 0.35 * (lung_l + lung_r)
    return np.clip(field, 0.0, 1.0)


def synthesize_capture(width: int, height: int, dose_factor: float,
                        seed: int | None = None) -> np.ndarray:
    """Return a uint16 (0-4095, 12-bit-style) noisy image.

    `dose_factor` in (0, 1] comes from `XraySourceState.relative_dose_factor()`
    - lower dose -> fewer photons -> more relative Poisson noise.
    """
    rng = np.random.default_rng(seed)
    clean = _phantom(width, height)

    max_photon_count = 20000.0  # arbitrary scale, not a calibrated detector value
    photon_count = max_photon_count * dose_factor
    signal = clean * photon_count

    poisson_noisy = rng.poisson(np.maximum(signal, 0)).astype(np.float64)
    electronic_noise = rng.normal(0.0, max_photon_count * 0.01, size=signal.shape)
    noisy = poisson_noisy + electronic_noise

    # normalize back to a 12-bit display range
    noisy = noisy / max(photon_count, 1.0) * 4095.0
    return np.clip(noisy, 0, 4095).astype(np.uint16)


def clean_reference(width: int, height: int) -> np.ndarray:
    """The noise-free phantom at 12-bit scale, for PSNR/SSIM comparisons
    against a denoised result.
    """
    return (_phantom(width, height) * 4095.0).astype(np.uint16)
