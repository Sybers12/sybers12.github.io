# NBTS Blood Bank Management System (Mfumo wa Usimamizi wa Banki ya Damu)

A web-based Blood Bank Management System modeled on the workflow of the
[National Blood Transfusion Service (NBTS), Tanzania](https://www.nbts.go.tz/).

Built with **FastAPI + SQLAlchemy + SQLite** and a vanilla JS frontend.
The interface is in English.

## Modules

| Module | Who | What |
|---|---|---|
| **Dashboard** | all roles | Blood group counts & percentages, TTI reactivity, product statistics |
| **Donors** | data clerk, head of donation, counselor, manager | Register donors (donation no., names, DOB, last donation date, times donated), search, donor history |
| **Donations** | phlebotomist, data clerk, head of donation, manager | Record donations with eligibility check (90-day deferral), view previous donation responses |
| **Recruiting** | recruiter | Request venues for donation drives, complete visits with actual turnout, send SMS to eligible/all donors, area statistics |
| **Laboratory** | lab tech, head of lab, quality, manager | Enter ABOD & TTI results linked to the donation number (machine ref), review, approve (head of lab / quality / manager), edit results & discrepancies, filter results by donation-no range (e.g. 23000–25000), blood group, TTI status; download PDF reports |
| **Blood Products** | lab tech, head of lab, manager | Sort blood into PRC, FFP, Platelets (PLT), Cryoprecipitate (CRYO); label products (quarantine → ready); issue to hospitals (blocked for reactive/unapproved blood) |
| **Council** | council users | View **approved** results only, filtered to their own council |

## Roles

`MANAGER`, `QUALITY`, `RECRUITER`, `HEAD_DONATION`, `COUNSELOR`, `HEAD_LAB`,
`PHLEBOTOMIST`, `LAB_TECH`, `DATA_CLERK`, `COUNCIL` — see
`backend/routers/auth.py` for the exact permission map.

## Run locally (Linux)

```bash
git clone https://github.com/Sybers12/sybers12.github.io
cd sybers12.github.io/bloodbank

python3 -m venv ~/myenv          # or use your existing venv
source ~/myenv/bin/activate

pip install -r requirements.txt
python3 -m backend.seed          # loads demo data (run once)
python3 run.py                   # serves on http://127.0.0.1:8500
```

Open **http://127.0.0.1:8500** in your browser.

## Demo accounts

All demo users use password **`demo123`**:

`manager`, `quality`, `recruiter`, `head_donation`, `counselor`,
`head_lab`, `phlebotomist`, `lab_tech`, `data_clerk`, `council`
(the council user only sees approved results for *Ilala* council).

## Notes

- SMS sending is **simulated**: messages are logged to the database
  (`sms_logs` table) so the workflow can be demonstrated without an SMS
  gateway. Wire `POST /api/sms` to a real gateway (e.g. Africa's Talking)
  for production.
- The database is created at `bloodbank/data/bloodbank.db` (git-ignored).
- PDF reports are generated with ReportLab at
  `GET /api/pdf/results` and `GET /api/pdf/products`.
