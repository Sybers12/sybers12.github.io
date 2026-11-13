import threading

from pydicom import Dataset
from pynetdicom import (
    AE,
    AllStoragePresentationContexts,
    VerificationPresentationContexts,
    debug_logger,
    evt,
)
from pynetdicom.sop_class import PatientRootQueryRetrieveInformationModelFind

from . import config
from .database import SessionLocal
from .ingest import ingest_dataset, store_dataset
from .models import Patient, Study

_find_model = PatientRootQueryRetrieveInformationModelFind


def _matches(value: str, query_value: str) -> bool:
    """DICOM-style wildcard matching (* and ?)."""
    if query_value == "" or query_value == "*":
        return True
    import fnmatch

    return fnmatch.fnmatchcase(value, query_value)


def handle_find(event):
    identifier = event.identifier
    query_level = str(getattr(identifier, "QueryRetrieveLevel", "STUDY")).upper()

    with SessionLocal() as db:
        if query_level == "PATIENT":
            rows = db.query(Patient).all()
            for patient in rows:
                if not _matches(patient.patient_id, str(getattr(identifier, "PatientID", "*"))):
                    continue
                if not _matches(patient.name, str(getattr(identifier, "PatientName", "*"))):
                    continue
                response = Dataset()
                response.QueryRetrieveLevel = "PATIENT"
                response.PatientName = patient.name.replace(" ", "^")
                response.PatientID = patient.patient_id
                response.PatientBirthDate = patient.birth_date
                response.PatientSex = patient.sex
                yield 0xFF00, response
            return

        query = db.query(Study).join(Patient, Study.patient_pk == Patient.id)
        patient_id = str(getattr(identifier, "PatientID", ""))
        if patient_id and patient_id != "*":
            query = query.filter(Patient.patient_id == patient_id)
        patient_name = str(getattr(identifier, "PatientName", ""))
        if patient_name and patient_name != "*":
            query = query.filter(Patient.name == patient_name.replace("^", " "))
        study_date = str(getattr(identifier, "StudyDate", ""))
        if study_date and study_date != "*":
            if "-" in study_date:
                start, end = study_date.split("-", 1)
                query = query.filter(Study.study_date >= start, Study.study_date <= end)
            else:
                query = query.filter(Study.study_date == study_date)
        modality = str(getattr(identifier, "ModalitiesInStudy", "")) or str(
            getattr(identifier, "Modality", "")
        )
        if modality and modality != "*":
            query = query.filter(Study.modality == modality)
        accession = str(getattr(identifier, "AccessionNumber", ""))
        if accession and accession != "*":
            query = query.filter(Study.accession_number == accession)
        study_uid = str(getattr(identifier, "StudyInstanceUID", ""))
        if study_uid and study_uid != "*":
            query = query.filter(Study.study_uid == study_uid)

        for study in query.all():
            response = Dataset()
            response.QueryRetrieveLevel = "STUDY"
            if "PatientName" in identifier:
                response.PatientName = study.patient.name.replace(" ", "^")
            if "PatientID" in identifier:
                response.PatientID = study.patient.patient_id
            if "StudyDate" in identifier:
                response.StudyDate = study.study_date
            if "StudyTime" in identifier:
                response.StudyTime = study.study_time
            if "Modality" in identifier:
                response.Modality = study.modality
            if "ModalitiesInStudy" in identifier:
                response.ModalitiesInStudy = study.modality
            if "StudyDescription" in identifier:
                response.StudyDescription = study.description
            if "AccessionNumber" in identifier:
                response.AccessionNumber = study.accession_number
            if "StudyInstanceUID" in identifier:
                response.StudyInstanceUID = study.study_uid
            if "ReferringPhysicianName" in identifier:
                response.ReferringPhysicianName = study.referring_physician.replace(" ", "^")
            yield 0xFF00, response


def handle_store(event):
    ds = event.dataset
    file_path = store_dataset(ds)
    try:
        ingest_dataset(ds, file_path)
        return 0x0000
    except Exception:
        return 0xA700


def start_dicom_server():
    ae = AE(ae_title=config.AE_TITLE)
    ae.add_supported_context(_find_model)
    for context in AllStoragePresentationContexts:
        ae.add_supported_context(context.abstract_syntax)
    for context in VerificationPresentationContexts:
        ae.add_supported_context(context.abstract_syntax)

    handlers = [(evt.EVT_C_STORE, handle_store), (evt.EVT_C_FIND, handle_find)]

    import logging

    server = ae.start_server(
        ("", config.DICOM_PORT),
        block=False,
        evt_handlers=handlers,
    )
    logging.getLogger(__name__).info(
        "DICOM server listening on port %d (AE title %s)", config.DICOM_PORT, config.AE_TITLE
    )
    return server


if __name__ == "__main__":
    debug_logger()
    server = start_dicom_server()
    threading.Event().wait()
