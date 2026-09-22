"""Package a simulated capture as a standard DICOM (DX modality) dataset
and send it via C-STORE to a real DICOM receiver.

This module only uses the public DICOM standard (via pydicom/pynetdicom) -
no vendor-specific protocol or format is involved, so it carries none of
the restrictions noted in pipeline/PLAN.md section 3-1. It's meant to feed
a sibling DICOM viewer project's "device bridge" C-STORE listener, so a
CAPTURE in this simulator shows up as an image in a real (if minimal)
DICOM viewer.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DX_STORAGE_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.1.1"  # Digital X-Ray Image Storage - For Presentation

BODY_PART_MAP = {
    "NONE": "",
    "CHEST": "CHEST",
    "ABDOMEN": "ABDOMEN",
    "EXTREMITY": "EXTREMITY",
    "SPINE": "SPINE",
}


def build_dataset(state, pixels: np.ndarray) -> FileDataset:
    """Build a minimal but valid DX dataset from the simulator's current
    state and a captured 12-bit pixel array (see noise_model.synthesize_capture).
    """
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = DX_STORAGE_SOP_CLASS
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.SOPClassUID = DX_STORAGE_SOP_CLASS
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

    now = datetime.datetime.now()
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1

    ds.Modality = "DX"
    ds.PatientName = "Simulated^Phantom"
    ds.PatientID = "SIM0001"
    ds.PatientBirthDate = ""
    ds.PatientSex = "O"

    ds.BodyPartExamined = BODY_PART_MAP.get(state.apr_region, "")
    ds.KVP = float(state.kvp)
    ds.XRayTubeCurrent = int(state.ma)
    ds.ExposureTime = 100  # ms, arbitrary fixed value - not modeled

    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = pixels.shape
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.astype(np.uint16).tobytes()

    ds.is_little_endian = True
    ds.is_implicit_VR = False
    return ds


def send_to_viewer(ds: FileDataset, host: str = "127.0.0.1", port: int = 11114,
                    calling_ae: str = "XRAYSIM", called_ae: str = "XRAYVIEWER") -> tuple[bool, str]:
    """C-STORE the dataset to a listening DICOM receiver. Returns
    (success, message) instead of raising, so a capture never fails just
    because no viewer happens to be listening right now.
    """
    from pynetdicom import AE
    from pynetdicom.sop_class import DigitalXRayImageStorageForPresentation

    ae = AE(ae_title=calling_ae)
    ae.add_requested_context(DigitalXRayImageStorageForPresentation)

    assoc = ae.associate(host, port, ae_title=called_ae)
    if not assoc.is_established:
        return False, f"could not associate with {host}:{port}"

    try:
        status = assoc.send_c_store(ds)
        if status and status.Status == 0x0000:
            return True, "C-STORE accepted"
        return False, f"C-STORE failed, status=0x{getattr(status, 'Status', -1):04X}"
    finally:
        assoc.release()
