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

SOP_CLASSES = {
    "CT": "1.2.840.10008.5.1.4.1.1.2",
    "MR": "1.2.840.10008.5.1.4.1.1.4",
    "CR": "1.2.840.10008.5.1.4.1.1.1",
    "DX": "1.2.840.10008.5.1.4.1.1.1.1",
    "MG": "1.2.840.10008.5.1.4.1.1.1.2",
    "US": "1.2.840.10008.5.1.4.1.1.3.1",
}


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


def xray_image(size: int = 1400, seed: int = 0, lateral: bool = False) -> np.ndarray:
    """Synthetic chest radiograph (PA or lateral), arbitrary units."""
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
        vessels = rng.random((size, size)) > 0.997
        img[lung & vessels] = 110.0
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
    if lateral:
        for side in (-1, 1):
            shoulder = _ellipse_mask(yy, xx, cy - size * 0.30, cx + side * size * 0.30,
                                     size * 0.07, size * 0.09)
            img[shoulder] = 45.0
        retro = _ellipse_mask(yy, xx, cy - size * 0.05, cx, size * 0.12, size * 0.06)
        img[retro] = 120.0
    else:
        for side in (-1, 1):
            clavicle = _ellipse_mask(yy, xx, cy - size * 0.33, cx + side * size * 0.14,
                                     size * 0.012, size * 0.11, angle=side * 0.35)
            img[clavicle] = 45.0
    return img


def opg_image(w: int = 1800, h: int = 1000, seed: int = 0) -> np.ndarray:
    """Synthetic dental panoramic radiograph (OPG): unrolled jaw with teeth."""
    rng = _rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t1 = np.arange(w) / w
    y_mand = h * (0.30 + 0.34 * np.sin(np.pi * t1))
    y_max = y_mand - h * 0.24
    y_occ = y_mand - h * 0.12

    img = np.full((h, w), 25.0) + rng.normal(0, 6, (h, w))

    mand = np.abs(yy - y_mand) < h * 0.075
    maxilla = np.abs(yy - y_max) < h * 0.065
    img[mand] = 95.0 + rng.normal(0, 14, img[mand].shape)
    img[maxilla] = 105.0 + rng.normal(0, 14, img[maxilla].shape)
    cort_m = np.abs(np.abs(yy - y_mand) - h * 0.075) < h * 0.012
    cort_x = np.abs(np.abs(yy - y_max) - h * 0.065) < h * 0.011
    img[cort_m] = 210.0 + rng.normal(0, 15, img[cort_m].shape)
    img[cort_x] = 200.0 + rng.normal(0, 15, img[cort_x].shape)

    for side in (0, 1):
        xe = side * (w - 1)
        ramus = _ellipse_mask(yy, xx, h * 0.30, xe, h * 0.17, w * 0.045)
        img[ramus] = 150.0 + rng.normal(0, 20, img[ramus].shape)
        condyle = _ellipse_mask(yy, xx, h * 0.13, xe, h * 0.035, w * 0.025)
        img[condyle] = 190.0

    for side in (-1, 1):
        sinus = _ellipse_mask(yy, xx, h * 0.16, w / 2 + side * w * 0.26, h * 0.12, w * 0.12)
        img[sinus] = 28.0 + rng.normal(0, 5, img[sinus].shape)
    nasal = _ellipse_mask(yy, xx, h * 0.14, w / 2, h * 0.11, w * 0.055)
    img[nasal] = 22.0

    for k in range(4):
        vert = _ellipse_mask(yy, xx, h * 0.78 + k * h * 0.055, w / 2, h * 0.028, w * 0.035)
        img[vert] = 130.0 + rng.normal(0, 10, img[vert].shape)

    n_teeth = 14
    for k in range(n_teeth):
        tk = (k + 0.5) / n_teeth
        cx_t = tk * w
        idx = min(w - 1, max(0, int(cx_t)))
        yo = y_occ[idx]
        molar = min(k, n_teeth - 1 - k) < 4
        crown_rx = w * (0.016 if molar else 0.011)
        crown_ry = h * (0.050 if molar else 0.042)
        crown = _ellipse_mask(yy, xx, yo, cx_t, crown_ry, crown_rx)
        img[crown] = 235.0 + rng.normal(0, 10, img[crown].shape)
        pulp = _ellipse_mask(yy, xx, yo, cx_t, crown_ry * 0.55, crown_rx * 0.4)
        img[pulp] = 120.0
        upper = tk < 0.5
        root_cy = yo - h * 0.085 if upper else yo + h * 0.085
        root = _ellipse_mask(yy, xx, root_cy, cx_t, h * 0.055, crown_rx * 0.55)
        img[root] = 175.0 + rng.normal(0, 12, img[root].shape)
        if molar:
            for off in (-1, 1):
                r2 = _ellipse_mask(yy, xx, root_cy, cx_t + off * crown_rx * 0.7,
                                   h * 0.05, crown_rx * 0.3)
                img[r2] = 175.0

    lesion = _ellipse_mask(yy, xx, y_mand[int(w * 0.72)] - h * 0.02, w * 0.72, h * 0.03, w * 0.018)
    img[lesion] = 60.0
    return img


def cbct_slice(z: int, n_slices: int, size: int = 200, seed: int = 0) -> np.ndarray:
    """Synthetic dental CBCT axial slice: jaw arch ring with teeth roots and canals."""
    rng = _rng(seed + z)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    cx = cy = size / 2.0
    r = np.sqrt(((xx - cx) / (size * 0.36)) ** 2 + ((yy - cy) / (size * 0.30)) ** 2)
    img = np.full((size, size), -500.0)
    interior = r <= 0.74
    img[interior] = 160.0 + rng.normal(0, 25, img[interior].shape)
    trab = rng.random((size, size)) > 0.93
    img[interior & trab] = 320.0
    ring = (r > 0.74) & (r < 1.0)
    img[ring] = 750.0 + rng.normal(0, 60, img[ring].shape)
    rim = (r >= 1.0) & (r < 1.06)
    img[rim] = 950.0 + rng.normal(0, 40, img[rim].shape)

    phase = z / max(1, n_slices - 1)
    if 0.28 <= phase <= 0.78:
        for a in np.linspace(0.18 * np.pi, 0.82 * np.pi, 8):
            tx = cx + 0.84 * size * 0.36 * math.cos(a)
            ty = cy + 0.84 * size * 0.30 * math.sin(a)
            tooth = (xx - tx) ** 2 + (yy - ty) ** 2 < (size * 0.035) ** 2
            img[tooth] = 1500.0 + rng.normal(0, 80, img[tooth].shape)
    for side in (-1, 1):
        canal = _ellipse_mask(yy, xx, cy + size * 0.06, cx + side * size * 0.17,
                              size * 0.05, size * 0.02, angle=side * 0.4)
        img[canal] = -450.0
    return img


def mg_image(w: int = 1400, h: int = 1700, seed: int = 0) -> np.ndarray:
    """Synthetic mammography (CC view): fatty/glandular tissue, mass, microcalcifications."""
    rng = _rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    breast = _ellipse_mask(yy, xx, h * 0.10, w / 2, h * 0.80, w * 0.44)
    img = np.full((h, w), 20.0)
    img[breast] = 190.0
    from PIL import Image as _Image
    small = _Image.fromarray(
        rng.normal(128, 40, (h // 60 + 1, w // 60 + 1)).astype(np.uint8), mode="L"
    )
    fat = np.asarray(small.resize((w, h), _Image.BICUBIC), dtype=np.float64) - 128.0
    img[breast] += fat[breast] * 1.1
    gland_w = np.clip(0.42 - 0.30 * (yy / h), 0, 0.42)
    gland = breast & (yy < h * 0.50) & (np.abs(xx - w / 2) < w * gland_w)
    img[gland] += 110.0 + rng.normal(0, 25, img[gland].shape)
    img[breast] += rng.normal(0, 11, img[breast].shape)
    pect = breast & (yy < h * 0.10)
    img[pect] = 330.0 + rng.normal(0, 15, img[pect].shape)
    rim = breast & ~_ellipse_mask(yy, xx, h * 0.10, w / 2, h * 0.785, w * 0.425)
    img[rim] = 80.0

    mass = _ellipse_mask(yy, xx, h * 0.55, w * 0.40, h * 0.030, w * 0.032)
    img[mass] = 430.0 + rng.normal(0, 15, img[mass].shape)
    for k in range(18):
        a = k * 2 * math.pi / 18
        spic = _ellipse_mask(yy, xx, h * 0.55 + h * 0.035 * math.sin(a),
                             w * 0.40 + w * 0.038 * math.cos(a),
                             h * 0.004, w * 0.012, angle=a)
        img[spic] = 380.0
    for k in range(30):
        px = int(w * 0.63 + rng.normal(0, w * 0.02))
        py = int(h * 0.34 + rng.normal(0, h * 0.03))
        if 0 <= py < h - 1 and 0 <= px < w - 1:
            img[py:py + 2, px:px + 2] = 620.0
    return img


def us_frames(n_frames: int = 24, size: int = 384, seed: int = 0) -> np.ndarray:
    """Synthetic ultrasound cine loop (grayscale sector with speckle and a pulsating chamber)."""
    rng = _rng(seed)
    w = size + 64
    yy, xx = np.mgrid[0:size, 0:w].astype(np.float64)
    cx = w / 2.0
    dx = xx - cx
    dy = yy - 10.0
    ang = np.arctan2(dx, dy)
    r = np.hypot(dx, dy)
    in_sector = (np.abs(ang) < 0.55) & (r < size * 0.95) & (r > 12.0)

    speckle = rng.normal(0, 1, (size // 2, w // 2))
    speckle = np.kron(speckle, np.ones((2, 2)))[:size, :w]
    gain = np.clip(1.25 - r / (size * 1.05), 0.12, 1.0)

    frames = np.zeros((n_frames, size, w))
    for f in range(n_frames):
        img = np.zeros((size, w))
        img[in_sector] = 5200.0 + speckle[in_sector] * 900.0
        img[in_sector] *= gain[in_sector]
        beat = 1.0 + 0.16 * math.sin(2 * math.pi * f / n_frames)
        vent = _ellipse_mask(yy, xx, size * 0.48, cx, size * 0.17 * beat, size * 0.13 * beat)
        img[vent] = 350.0
        wall_top = size * (0.30 + 0.012 * math.sin(2 * math.pi * f / n_frames))
        valve = (np.abs(yy - wall_top - 0.10 * np.abs(dx)) < 3.0) & (np.abs(dx) < size * 0.14)
        img[valve] = 7800.0
        probe = (r < 12.0) & (np.abs(ang) < 0.55)
        img[probe] = 8600.0
        frames[f] = img
    return frames


def build_dataset(img: np.ndarray, *, modality, patient, study_uid, series_uid,
                  sop_uid, series_number, instance_number, series_desc,
                  body_part, wc, ww, pixel_spacing, slice_thickness,
                  study_date, study_time, study_desc, accession, bits_stored=16,
                  rescale_slope=1.0, rescale_intercept=0.0) -> Dataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SOP_CLASSES.get(modality, SOP_CLASSES["CT"])
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
    if modality in ("CT", "CBCT"):
        ds.ImagePositionPatient = [0.0, 0.0, float(instance_number * slice_thickness)]
    if img.ndim == 3:
        ds.NumberOfFrames = img.shape[0]
        ds.Rows, ds.Columns = img.shape[1], img.shape[2]
    else:
        ds.Rows, ds.Columns = img.shape
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.PixelData = img.astype(np.int16).tobytes()
    return ds


def seed():
    init_db()
    today = datetime.date.today().strftime("%Y%m%d")
    patients = {
        "anna": {"id": "P-100001", "name": "JOHANSSON^ANNA", "birth": "19720314", "sex": "F"},
        "erik": {"id": "P-100002", "name": "LARSSON^ERIK", "birth": "19581102", "sex": "M"},
        "maria": {"id": "P-100003", "name": "NILSSON^MARIA", "birth": "19840627", "sex": "F"},
        "oskar": {"id": "P-100004", "name": "KARLSSON^OSKAR", "birth": "19690130", "sex": "M"},
        "sofia": {"id": "P-100005", "name": "LINDQVIST^SOFIA", "birth": "19751009", "sex": "F"},
        "henrik": {"id": "P-100006", "name": "BERG^HENRIK", "birth": "19920721", "sex": "M"},
        "lisa": {"id": "P-100007", "name": "EK^LISA", "birth": "19520218", "sex": "F"},
    }
    jobs = []

    def add(img, *, modality, patient, series_desc, body_part, wc, ww,
            pixel_spacing, slice_thickness, study_desc, accession,
            series_number=1, instance_number=1, study_uid=None, series_uid=None,
            study_time="090000", bits_stored=16, rescale_slope=1.0, rescale_intercept=0.0):
        study_uid = study_uid or generate_uid()
        series_uid = series_uid or generate_uid()
        ds = build_dataset(
            img, modality=modality, patient=patient, study_uid=study_uid,
            series_uid=series_uid, sop_uid=generate_uid(), series_number=series_number,
            instance_number=instance_number, series_desc=series_desc,
            body_part=body_part, wc=wc, ww=ww, pixel_spacing=pixel_spacing,
            slice_thickness=slice_thickness, study_date=today, study_time=study_time,
            study_desc=study_desc, accession=accession, bits_stored=bits_stored,
            rescale_slope=rescale_slope, rescale_intercept=rescale_intercept,
        )
        jobs.append(ds)
        return study_uid, series_uid

    ct_study = generate_uid()
    ct_series = generate_uid()
    n = 48
    for i in range(n):
        add(ct_slice(i, n, seed=7), modality="CT", patient=patients["anna"],
            series_desc="CHEST/AXIAL 5mm", body_part="CHEST", wc=40, ww=400,
            pixel_spacing=[0.7, 0.7], slice_thickness=5.0,
            study_desc="CT CHEST WITHOUT CONTRAST", accession="ACC-2024-0001",
            series_number=2, instance_number=i + 1, study_uid=ct_study,
            series_uid=ct_series, study_time="091500")

    mr_study = generate_uid()
    mr_series = generate_uid()
    n = 24
    for i in range(n):
        add(mr_slice(i, n, seed=42), modality="MR", patient=patients["erik"],
            series_desc="AX T1 FLAIR", body_part="BRAIN", wc=700, ww=900,
            pixel_spacing=[0.9, 0.9], slice_thickness=4.0,
            study_desc="MR BRAIN WITHOUT CONTRAST", accession="ACC-2024-0002",
            series_number=3, instance_number=i + 1, study_uid=mr_study,
            series_uid=mr_series, study_time="131000")

    add(xray_image(seed=5), modality="CR", patient=patients["maria"],
        series_desc="PA CHEST", body_part="CHEST", wc=120, ww=300,
        pixel_spacing=[0.15, 0.15], slice_thickness=1.0,
        study_desc="CHEST 2V", accession="ACC-2024-0003", study_time="154530")

    dx_study = generate_uid()
    add(xray_image(size=1600, seed=11), modality="DX", patient=patients["oskar"],
        series_desc="CHEST PA", body_part="CHEST", wc=130, ww=340,
        pixel_spacing=[0.14, 0.14], slice_thickness=1.0,
        study_desc="DX CHEST 2V", accession="ACC-2024-0004",
        series_number=1, study_uid=dx_study, study_time="082000")
    add(xray_image(size=1600, seed=12, lateral=True), modality="DX", patient=patients["oskar"],
        series_desc="CHEST LATERAL", body_part="CHEST", wc=140, ww=380,
        pixel_spacing=[0.14, 0.14], slice_thickness=1.0,
        study_desc="DX CHEST 2V", accession="ACC-2024-0004",
        series_number=2, study_uid=dx_study, study_time="082100")

    add(opg_image(seed=3), modality="OPG", patient=patients["henrik"],
        series_desc="OPG PANORAMIC", body_part="JAW", wc=95, ww=260,
        pixel_spacing=[0.12, 0.12], slice_thickness=1.0,
        study_desc="OPG DENTAL PANORAMIC", accession="ACC-2024-0005",
        study_time="100500")

    cbct_study = generate_uid()
    cbct_series = generate_uid()
    n = 96
    for i in range(n):
        add(cbct_slice(i, n, seed=9), modality="CBCT", patient=patients["henrik"],
            series_desc="MANDIBLE AXIAL 0.3mm", body_part="JAW", wc=350, ww=1800,
            pixel_spacing=[0.3, 0.3], slice_thickness=0.3,
            study_desc="CBCT MANDIBLE", accession="ACC-2024-0006",
            series_number=1, instance_number=i + 1, study_uid=cbct_study,
            series_uid=cbct_series, study_time="101500")

    mg_study = generate_uid()
    add(mg_image(seed=21), modality="MG", patient=patients["sofia"],
        series_desc="RCC", body_part="BREAST", wc=330, ww=620,
        pixel_spacing=[0.07, 0.07], slice_thickness=1.0,
        study_desc="MG SCREENING BILATERAL", accession="ACC-2024-0007",
        series_number=1, study_uid=mg_study, study_time="113000")
    add(mg_image(seed=22), modality="MG", patient=patients["sofia"],
        series_desc="LCC", body_part="BREAST", wc=330, ww=620,
        pixel_spacing=[0.07, 0.07], slice_thickness=1.0,
        study_desc="MG SCREENING BILATERAL", accession="ACC-2024-0007",
        series_number=2, study_uid=mg_study, study_time="113100")

    add(us_frames(n_frames=24, seed=31), modality="US", patient=patients["lisa"],
        series_desc="A4C CINE LOOP", body_part="HEART", wc=4200, ww=8000,
        pixel_spacing=[0.4, 0.4], slice_thickness=1.0,
        study_desc="US ECHOCARDIOGRAM", accession="ACC-2024-0008",
        study_time="140000")

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
