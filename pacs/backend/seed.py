import datetime
import math
import os
import sys

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from backend import config
from backend.database import SessionLocal, init_db
from backend.ingest import ingest_dataset, store_dataset
from backend.models import Study


def _rng(seed):
    return np.random.default_rng(seed)


def _ellipse_mask(yy, xx, cy, cx, ry, rx, angle=0.0):
    ca, sa = math.cos(angle), math.sin(angle)
    dy, dx = yy - cy, xx - cx
    u = (dx * ca + dy * sa) / rx
    v = (-dx * sa + dy * ca) / ry
    return (u * u + v * v) <= 1.0


def ct_slice(z: int, n_slices: int, size: int = 512, seed: int = 0) -> np.ndarray:
    """Synthetic axial CT slice of a thorax in HU, with lungs, spine, ribs and a lesion."""
    rng = _rng(seed + z)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    cx = cy = size / 2.0
    body = _ellipse_mask(yy, xx, cy, cx, size * 0.36, size * 0.42)
    img = np.full((size, size), -1000.0)
    img[body] = 40.0 + rng.normal(0, 8, img[body].shape)

    phase = z / max(1, n_slices - 1)
    lung_top, lung_bottom = 0.22, 0.85
    in_lungs = lung_top <= phase <= lung_bottom
    if in_lungs:
        t = (phase - lung_top) / (lung_bottom - lung_top)
        grow = 0.75 + 0.25 * math.sin(math.pi * t)
        for side in (-1, 1):
            lung = _ellipse_mask(yy, xx, cy - size * 0.03, cx + side * size * 0.175,
                                 size * 0.21 * grow, size * 0.135 * grow, angle=side * 0.08)
            img[lung & body] = -790.0 + rng.normal(0, 30, img[lung & body].shape)
            vessels = rng.random((size, size)) > 0.998
            img[lung & body & vessels] = 55.0
        lesion_cy = cy - size * 0.09
        lesion_cx = cx + size * 0.175
        lesion_r = size * 0.024
        lesion = _ellipse_mask(yy, xx, lesion_cy, lesion_cx, lesion_r, lesion_r)
        img[lesion] = 55.0 + rng.normal(0, 10, img[lesion].shape)

    trachea = _ellipse_mask(yy, xx, cy - size * 0.02, cx, size * 0.018, size * 0.018)
    if in_lungs and phase < 0.5:
        img[trachea] = -900.0

    spine_y = cy + size * 0.265
    spine = _ellipse_mask(yy, xx, spine_y, cx, size * 0.055, size * 0.065)
    img[spine] = 330.0 + rng.normal(0, 30, img[spine].shape)
    canal = _ellipse_mask(yy, xx, spine_y - size * 0.005, cx, size * 0.016, size * 0.018)
    img[canal] = 80.0

    heart = _ellipse_mask(yy, xx, cy + size * 0.09, cx - size * 0.06,
                          size * 0.13, size * 0.105, angle=-0.3)
    img[heart & body] = 45.0 + rng.normal(0, 6, img[heart & body].shape)
    aorta = _ellipse_mask(yy, xx, cy + size * 0.02, cx - size * 0.015, size * 0.02, size * 0.02)
    img[aorta & body] = 90.0

    outer = _ellipse_mask(yy, xx, cy, cx, size * 0.305, size * 0.365)
    inner = _ellipse_mask(yy, xx, cy, cx, size * 0.285, size * 0.345)
    theta = np.arctan2(yy - cy, xx - cx)
    ribs = outer & ~inner & (np.sin(9 * theta + 0.4) > 0.1)
    posterior = yy > cy + size * 0.05
    img[ribs & body & posterior] = 280.0
    sternum = _ellipse_mask(yy, xx, cy - size * 0.30, cx, size * 0.035, size * 0.012)
    img[sternum & body] = 300.0

    skin = body & ~_ellipse_mask(yy, xx, cy, cx, size * 0.345, size * 0.405)
    img[skin] = 160.0
    return img


def mr_slice(z: int, n_slices: int, size: int = 256, seed: int = 100) -> np.ndarray:
    """Synthetic axial MR brain slice (arbitrary units, T1-like)."""
    rng = _rng(seed + z)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    cx = cy = size / 2.0
    head = _ellipse_mask(yy, xx, cy, cx, size * 0.40, size * 0.32)
    img = np.zeros((size, size))
    img[head] = 900.0 + rng.normal(0, 30, img[head].shape)
    skull = head & ~_ellipse_mask(yy, xx, cy, cx, size * 0.36, size * 0.28)
    img[skull] = 250.0
    brain = _ellipse_mask(yy, xx, cy, cx, size * 0.35, size * 0.27)
    img[brain] = 700.0 + rng.normal(0, 20, img[brain].shape)
    midsagittal = np.abs(xx - cx) < 1.5
    img[brain & midsagittal] = 400.0
    for side in (-1, 1):
        ventricle = _ellipse_mask(yy, xx, cy - size * 0.04, cx + side * size * 0.07,
                                  size * 0.09, size * 0.03)
        img[ventricle] = 120.0
    phase = z / max(1, n_slices - 1)
    if 0.35 <= phase <= 0.65:
        tumor = _ellipse_mask(yy, xx, cy - size * 0.12, cx + size * 0.10, size * 0.05, size * 0.045)
        img[tumor] = 950.0
    return img


def cr_image(size: int = 1024, seed: int = 0) -> np.ndarray:
    """Synthetic chest radiograph (arbitrary units)."""
    rng = _rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    cx = cy = size / 2.0
    chest = _ellipse_mask(yy, xx, cy, cx, size * 0.44, size * 0.36)
    img = np.full((size, size), 60.0)
    img[chest] = 140.0 + rng.normal(0, 10, img[chest].shape)
    for side in (-1, 1):
        lung = _ellipse_mask(yy, xx, cy + size * 0.02, cx + side * size * 0.17,
                             size * 0.24, size * 0.13, angle=side * 0.12)
        img[lung] = 90.0 + rng.normal(0, 6, img[lung].shape)
    spine = _ellipse_mask(yy, xx, cy, cx, size * 0.30, size * 0.025)
    img[spine] = 40.0
    for k in range(8):
        y = cy - size * 0.22 + k * size * 0.06
        vertebra = _ellipse_mask(yy, xx, y, cx, size * 0.025, size * 0.035)
        img[vertebra] = 30.0
    for k in range(6):
        for side in (-1, 1):
            rib = _ellipse_mask(yy, xx, cy - size * 0.15 + k * size * 0.06,
                                cx + side * size * 0.16, size * 0.16, size * 0.008,
                                angle=side * 0.6)
            img[rib & chest] = 55.0
    heart = _ellipse_mask(yy, xx, cy + size * 0.10, cx + size * 0.07, size * 0.14, size * 0.11)
    img[heart] = 150.0
    return img


def build_dataset(img: np.ndarray, *, modality, patient, study_uid, series_uid,
                  sop_uid, series_number, instance_number, series_desc,
                  body_part, wc, ww, pixel_spacing, slice_thickness,
                  study_date, study_time, study_desc, accession, bits_stored=16,
                  rescale_slope=1.0, rescale_intercept=0.0) -> Dataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2" if modality == "CT" else "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.Modality = modality
    ds.PatientName = patient["name"]
    ds.PatientID = patient["id"]
    ds.PatientBirthDate = patient["birth"]
    ds.PatientSex = patient["sex"]
    ds.StudyDate = study_date
    ds.StudyTime = study_time
    ds.StudyDescription = study_desc
    ds.SeriesDescription = series_desc
    ds.AccessionNumber = accession
    ds.ReferringPhysicianName = "ANDERSSON^EVA"
    ds.BodyPartExamined = body_part
    ds.SeriesNumber = series_number
    ds.InstanceNumber = instance_number
    ds.Rows, ds.Columns = img.shape
    ds.PixelSpacing = pixel_spacing
    ds.SliceThickness = slice_thickness
    ds.WindowCenter = wc
    ds.WindowWidth = ww
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.SamplesPerPixel = 1
    ds.BitsAllocated = bits_stored
    ds.BitsStored = bits_stored
    ds.HighBit = bits_stored - 1
    ds.PixelRepresentation = 1
    ds.RescaleSlope = rescale_slope
    ds.RescaleIntercept = rescale_intercept
    if modality == "CT":
        ds.ImagePositionPatient = [0.0, 0.0, float(instance_number * slice_thickness)]
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.PixelData = img.astype(np.int16).tobytes()
    return ds


def seed():
    init_db()
    patients = {
        "anna": {"id": "P-100001", "name": "JOHANSSON^ANNA", "birth": "19720314", "sex": "F"},
        "erik": {"id": "P-100002", "name": "LARSSON^ERIK", "birth": "19581102", "sex": "M"},
        "maria": {"id": "P-100003", "name": "NILSSON^MARIA", "birth": "19840627", "sex": "F"},
    }
    jobs = []

    ct_study = generate_uid()
    ct_series = generate_uid()
    n = 48
    for i in range(n):
        img = ct_slice(i, n, seed=7)
        sop = generate_uid()
        ds = build_dataset(
            img, modality="CT", patient=patients["anna"], study_uid=ct_study,
            series_uid=ct_series, sop_uid=sop, series_number=2,
            instance_number=i + 1, series_desc="CHEST/AXIAL 5mm", body_part="CHEST",
            wc=40, ww=400, pixel_spacing=[0.7, 0.7], slice_thickness=5.0,
            study_date=datetime.date.today().strftime("%Y%m%d"), study_time="091500",
            study_desc="CT CHEST WITHOUT CONTRAST", accession="ACC-2024-0001",
        )
        jobs.append(ds)

    mr_study = generate_uid()
    mr_series = generate_uid()
    n = 24
    for i in range(n):
        img = mr_slice(i, n, seed=42)
        sop = generate_uid()
        ds = build_dataset(
            img, modality="MR", patient=patients["erik"], study_uid=mr_study,
            series_uid=mr_series, sop_uid=sop, series_number=3,
            instance_number=i + 1, series_desc="AX T1 FLAIR", body_part="BRAIN",
            wc=700, ww=900, pixel_spacing=[0.9, 0.9], slice_thickness=4.0,
            study_date=datetime.date.today().strftime("%Y%m%d"), study_time="131000",
            study_desc="MR BRAIN WITHOUT CONTRAST", accession="ACC-2024-0002",
        )
        jobs.append(ds)

    cr_study = generate_uid()
    cr_series = generate_uid()
    img = cr_image(seed=5)
    ds = build_dataset(
        img, modality="CR", patient=patients["maria"], study_uid=cr_study,
        series_uid=cr_series, sop_uid=generate_uid(), series_number=1,
        instance_number=1, series_desc="PA CHEST", body_part="CHEST",
        wc=120, ww=300, pixel_spacing=[0.15, 0.15], slice_thickness=1.0,
        study_date=datetime.date.today().strftime("%Y%m%d"), study_time="154530",
        study_desc="CHEST 2V", accession="ACC-2024-0003",
    )
    jobs.append(ds)

    with SessionLocal() as db:
        if db.query(Study).count() > 0:
            print("Database already seeded; skipping.")
            return

    for ds in jobs:
        path = store_dataset(ds)
        ingest_dataset(ds, path)
    print(f"Seeded {len(jobs)} DICOM instances into {config.DICOM_DIR}")


if __name__ == "__main__":
    seed()
