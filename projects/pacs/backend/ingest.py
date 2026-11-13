import os

from pydicom import Dataset

from . import config
from .database import SessionLocal
from .models import Instance, Patient, Series, Study


def _first(ds: Dataset, keyword: str, default: str = "") -> str:
    value = getattr(ds, keyword, default)
    if value is None:
        return default
    return str(value)


def store_dataset(ds: Dataset) -> str:
    """Write a pydicom Dataset to the DICOM store and return its path."""
    sop_uid = str(ds.SOPInstanceUID)
    path = os.path.join(config.DICOM_DIR, f"{sop_uid}.dcm")
    ds.save_as(path, enforce_file_format=True)
    return path


def ingest_dataset(ds: Dataset, file_path: str) -> dict:
    """Insert or update patient/study/series/instance rows for a DICOM dataset."""
    sop_uid = str(ds.SOPInstanceUID)
    patient_id = _first(ds, "PatientID", "UNKNOWN")
    study_uid = str(getattr(ds, "StudyInstanceUID", sop_uid))
    series_uid = str(getattr(ds, "SeriesInstanceUID", sop_uid))

    pixel_spacing = [1.0, 1.0]
    spacing = getattr(ds, "PixelSpacing", None)
    if spacing is not None and len(spacing) >= 2:
        pixel_spacing = [float(spacing[0]), float(spacing[1])]

    def _num(keyword, default):
        value = getattr(ds, keyword, None)
        if value is None:
            return default
        if isinstance(value, (list, tuple)):
            value = value[0]
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    modality = _first(ds, "Modality", "")
    with SessionLocal() as db:
        patient = db.query(Patient).filter_by(patient_id=patient_id).one_or_none()
        if patient is None:
            patient = Patient(
                patient_id=patient_id,
                name=_first(ds, "PatientName", "UNKNOWN^PATIENT").replace("^", " "),
                birth_date=_first(ds, "PatientBirthDate", ""),
                sex=_first(ds, "PatientSex", ""),
            )
            db.add(patient)
            db.flush()

        study = db.query(Study).filter_by(study_uid=study_uid).one_or_none()
        if study is None:
            study = Study(
                study_uid=study_uid,
                patient_pk=patient.id,
                study_date=_first(ds, "StudyDate", ""),
                study_time=_first(ds, "StudyTime", ""),
                modality=modality,
                description=_first(ds, "StudyDescription", ""),
                accession_number=_first(ds, "AccessionNumber", ""),
                referring_physician=_first(ds, "ReferringPhysicianName", "").replace("^", " "),
            )
            db.add(study)
            db.flush()

        series = db.query(Series).filter_by(series_uid=series_uid).one_or_none()
        if series is None:
            series = Series(
                series_uid=series_uid,
                study_pk=study.id,
                modality=modality,
                description=_first(ds, "SeriesDescription", ""),
                series_number=int(getattr(ds, "SeriesNumber", 0) or 0),
                body_part=_first(ds, "BodyPartExamined", ""),
            )
            db.add(series)
            db.flush()

        instance = db.query(Instance).filter_by(sop_uid=sop_uid).one_or_none()
        if instance is None:
            instance = Instance(sop_uid=sop_uid, series_pk=series.id)
            db.add(instance)

        instance.instance_number = int(getattr(ds, "InstanceNumber", 1) or 1)
        instance.file_path = file_path
        instance.rows = int(getattr(ds, "Rows", 0) or 0)
        instance.cols = int(getattr(ds, "Columns", 0) or 0)
        instance.number_of_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        instance.window_center = _num("WindowCenter", 0.0)
        instance.window_width = _num("WindowWidth", 0.0)
        instance.pixel_spacing_x = pixel_spacing[0]
        instance.pixel_spacing_y = pixel_spacing[1]
        instance.slice_thickness = _num("SliceThickness", 1.0)
        instance.rescale_slope = _num("RescaleSlope", 1.0)
        instance.rescale_intercept = _num("RescaleIntercept", 0.0)
        instance.photometric = _first(ds, "PhotometricInterpretation", "MONOCHROME2")

        db.commit()
        return {
            "patient": patient_id,
            "study": study_uid,
            "series": series_uid,
            "instance": sop_uid,
        }
