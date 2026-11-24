# OpenPACS

A lightweight, open PACS (Picture Archiving and Communication System) inspired by
the workflow of commercial enterprise imaging platforms like Sectra. It combines a
standards-compliant DICOM network server, a searchable study worklist, and a fast
web-based image viewer in a single Python service.

## Features

- **DICOM network server** (pynetdicom): C-STORE SCP (all storage SOP classes),
  C-FIND SCP (Patient Root, patient and study level, wildcard matching), C-ECHO.
- **REST API** (FastAPI): study worklist with filters, series/instance listing,
  windowed frame rendering, series thumbnails, HTTP DICOM upload.
- **Web viewer**: modern dark radiology-style UI with
  - study worklist (search by patient, date range, one-click modality chips)
  - color-coded modality badges (CT, MR, CR, DX, OPG, CBCT, MG, US)
  - series thumbnails sidebar
  - window/level (drag), zoom (drag or wheel), pan, invert
  - window presets (soft tissue / lung / bone)
  - length measurement in mm (uses PixelSpacing)
  - slice slider + keyboard navigation (← →), DICOM corner overlays
  - cine playback (play/pause + frame scrubbing) for multi-frame studies such as
    ultrasound loops
- **Synthetic demo data**: seeder generates studies across 8 modalities —
  CT chest (with a lung lesion), MR brain (with a tumor), CR and DX chest X-rays
  (PA + lateral), dental OPG panoramic, dental CBCT volume, mammography (RCC/LCC
  with mass and microcalcifications), and a multi-frame ultrasound cine loop —
  no PHI, safe for demos.

## Quick start

```bash
pip install -r requirements.txt
python3 -m backend.seed        # generate demo studies (skips if already seeded)
python3 run.py
```

- Web UI: http://127.0.0.1:8000
- REST API: http://127.0.0.1:8000/api/studies
- DICOM listener: `OPENPACS` on port **11112**

## Configuration (env vars)

| Variable          | Default  | Purpose                    |
|-------------------|----------|----------------------------|
| `PACS_HTTP_PORT`  | `8000`   | Web UI + REST API port     |
| `PACS_DICOM_PORT` | `11112`  | DICOM listener port        |
| `PACS_AE_TITLE`   | `OPENPACS` | Server AE title          |

## Sending images to the PACS

Any DICOM-conformant SCU (or tools like `storescu` from dcmtk) can push images:

```python
from pydicom import dcmread
from pynetdicom import AE
from pynetdicom.sop_class import CTImageStorage

ae = AE(ae_title="MY_SCU")
ae.add_requested_context(CTImageStorage)
assoc = ae.associate("127.0.0.1", 11112, ae_title="OPENPACS")
assoc.send_c_store(dcmread("image.dcm"))
assoc.release()
```

You can also upload `.dcm` files directly in the web UI ("Upload DICOM") or via
`POST /api/dicom/upload` (multipart, field `files`).

## REST API overview

| Endpoint | Description |
|---|---|
| `GET /api/studies?patient=&modality=&date_from=&date_to=` | Worklist |
| `GET /api/studies/{study_uid}` | Study detail + series |
| `GET /api/series/{series_uid}/instances` | Instance metadata |
| `GET /api/instances/{sop_uid}/frame?wc=&ww=&invert=` | Windowed PNG frame |
| `GET /api/series/{series_uid}/thumbnail` | Series thumbnail |
| `POST /api/dicom/upload` | Store DICOM files |

## Project layout

```
backend/
  config.py         ports and data paths
  database.py       SQLAlchemy engine/session
  models.py         Patient / Study / Series / Instance
  ingest.py         DICOM dataset -> database upsert
  imaging.py        modality LUT, window/level, PNG rendering
  dicom_server.py   C-STORE / C-FIND / C-ECHO SCP
  seed.py           synthetic demo studies
  routers/          REST endpoints
frontend/           single-page viewer (vanilla JS)
run.py              starts REST API + DICOM server
data/               SQLite DB and DICOM object store (created at runtime)
```

## Not included (vs. commercial PACS)

This is an educational/demo system. Commercial platforms add, among others:
DICOM TLS and authentication, IHE profiles (SWF, XDS), HL7/FHIR RIS integration,
C-MOVE/C-GET retrieval, routing rules, compression (JPEG-2000), audit trails,
high availability, and regulatory clearance (CE/FDA). Do not use for clinical care.
