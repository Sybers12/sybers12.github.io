from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydicom import dcmread
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..imaging import get_frame, render_png, thumbnail_png
from ..ingest import ingest_dataset, store_dataset
from ..models import Instance, Patient, Series, Study
from .deps import get_db

router = APIRouter(prefix="/api")


def _study_dict(db: Session, study: Study) -> dict:
    patient = db.query(Patient).filter_by(id=study.patient_pk).one_or_none()
    series_count = db.query(Series).filter_by(study_pk=study.id).count()
    image_count = (
        db.query(Instance)
        .join(Series, Instance.series_pk == Series.id)
        .filter(Series.study_pk == study.id)
        .count()
    )
    return {
        "id": study.id,
        "study_uid": study.study_uid,
        "patient_id": patient.patient_id if patient else "",
        "patient_name": patient.name if patient else "",
        "birth_date": patient.birth_date if patient else "",
        "sex": patient.sex if patient else "",
        "study_date": study.study_date,
        "study_time": study.study_time,
        "modality": study.modality,
        "description": study.description,
        "accession_number": study.accession_number,
        "referring_physician": study.referring_physician,
        "series_count": series_count,
        "image_count": image_count,
    }


def _series_dict(db: Session, series: Series) -> dict:
    count = db.query(Instance).filter_by(series_pk=series.id).count()
    return {
        "id": series.id,
        "series_uid": series.series_uid,
        "study_uid": series.study.study_uid,
        "modality": series.modality,
        "description": series.description,
        "series_number": series.series_number,
        "body_part": series.body_part,
        "image_count": count,
    }


def _instance_dict(instance: Instance) -> dict:
    return {
        "id": instance.id,
        "sop_uid": instance.sop_uid,
        "instance_number": instance.instance_number,
        "rows": instance.rows,
        "cols": instance.cols,
        "number_of_frames": instance.number_of_frames,
        "window_center": instance.window_center,
        "window_width": instance.window_width,
        "pixel_spacing": [instance.pixel_spacing_x, instance.pixel_spacing_y],
        "slice_thickness": instance.slice_thickness,
    }


@router.get("/studies")
def list_studies(
    patient: str = "",
    modality: str = "",
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(Study).join(Patient, Study.patient_pk == Patient.id)
    if patient:
        like = f"%{patient}%"
        query = query.filter(
            (Patient.name.ilike(like)) | (Patient.patient_id.ilike(like))
        )
    if modality:
        query = query.filter(Study.modality == modality.upper())
    if date_from:
        query = query.filter(Study.study_date >= date_from)
    if date_to:
        query = query.filter(Study.study_date <= date_to)
    studies = query.order_by(Study.study_date.desc(), Study.id.desc()).all()
    return [_study_dict(db, s) for s in studies]


@router.get("/studies/{study_uid}")
def get_study(study_uid: str, db: Session = Depends(get_db)):
    study = db.query(Study).filter_by(study_uid=study_uid).one_or_none()
    if study is None:
        raise HTTPException(404, "Study not found")
    result = _study_dict(db, study)
    result["series"] = [
        _series_dict(db, s)
        for s in db.query(Series).filter_by(study_pk=study.id).order_by(Series.series_number)
    ]
    return result


@router.get("/series/{series_uid}/instances")
def list_instances(series_uid: str, db: Session = Depends(get_db)):
    series = db.query(Series).filter_by(series_uid=series_uid).one_or_none()
    if series is None:
        raise HTTPException(404, "Series not found")
    instances = (
        db.query(Instance)
        .filter_by(series_pk=series.id)
        .order_by(Instance.instance_number)
        .all()
    )
    return [_instance_dict(i) for i in instances]


@router.get("/instances/{sop_uid}/frame")
def get_instance_frame(
    sop_uid: str,
    frame: int = Query(0, ge=0),
    wc: float | None = None,
    ww: float | None = None,
    invert: bool = False,
    db: Session = Depends(get_db),
):
    instance = db.query(Instance).filter_by(sop_uid=sop_uid).one_or_none()
    if instance is None:
        raise HTTPException(404, "Instance not found")
    ds = dcmread(instance.file_path)
    pixels = get_frame(ds, frame)
    center = instance.window_center if wc is None else wc
    width = instance.window_width if ww is None else ww
    if center == 0 and width == 0:
        width = float(pixels.max() - pixels.min()) or 1.0
        center = float((pixels.max() + pixels.min()) / 2.0)
    png = render_png(pixels, center, width, invert=invert)
    return Response(content=png, media_type="image/png")


@router.get("/series/{series_uid}/thumbnail")
def get_series_thumbnail(series_uid: str, db: Session = Depends(get_db)):
    series = db.query(Series).filter_by(series_uid=series_uid).one_or_none()
    if series is None:
        raise HTTPException(404, "Series not found")
    instance = (
        db.query(Instance)
        .filter_by(series_pk=series.id)
        .order_by(Instance.instance_number)
        .first()
    )
    if instance is None:
        raise HTTPException(404, "Series has no images")
    ds = dcmread(instance.file_path)
    return Response(content=thumbnail_png(ds), media_type="image/png")


@router.post("/dicom/upload")
async def upload_dicom(files: list[UploadFile] = File(...)):
    results = []
    for upload in files:
        content = await upload.read()
        from io import BytesIO

        ds = dcmread(BytesIO(content), force=False)
        path = store_dataset(ds)
        results.append(ingest_dataset(ds, path))
    return {"stored": len(results), "results": results}
