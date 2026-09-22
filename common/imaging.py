"""Shared pixel-array -> preview-image conversion.

Kept in one place so the simulator (writing a quick-look PNG) and the
console app (decoding a round-tripped DICOM file) never implement the
same bit-depth normalization twice and drift apart - the sibling
dicom-xray-viewer project hit exactly that kind of duplication bug once
(see its docs/AI_SEGMENTATION_CLASSIFICATION_PLAN.md section 4-2).
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def to_preview_image(pixels: np.ndarray, bit_depth: int = 12) -> Image.Image:
    """Normalize an integer pixel array at the given bit depth to an 8-bit
    grayscale PIL image for on-screen preview.
    """
    max_val = (1 << bit_depth) - 1
    img8 = (pixels.astype("float32") / max_val * 255.0).clip(0, 255).astype("uint8")
    return Image.fromarray(img8, mode="L")


def load_capture_preview(png_path) -> Image.Image:
    return Image.open(png_path)


def load_dicom_preview(dicom_path) -> Image.Image:
    """Decode a .dcm file's actual PixelData back into a preview image -
    an independent round-trip check that what a DICOM receiver would see
    matches what the simulator captured, not just a re-display of the
    same in-memory array.
    """
    import pydicom

    ds = pydicom.dcmread(dicom_path)
    pixels = ds.pixel_array
    bits_stored = int(getattr(ds, "BitsStored", 12))
    return to_preview_image(pixels, bit_depth=bits_stored)
