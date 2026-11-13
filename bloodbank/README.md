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
| **Hospital Portal** | hospital users | View blood products issued to their hospital, with location |

## Roles

`ADMIN`, `MANAGER`, `QUALITY` (quality control manager), `HOSPITAL`, `RECRUITER`,
`HEAD_DONATION`, `COUNSELOR`, `HEAD_LAB`, `PHLEBOTOMIST`, `LAB_TECH`,
`DATA_CLERK`, `COUNCIL` — see `auth.py` for the exact permission map.

New users can self-register on the login page (**Create an account**) choosing a
category — Admin, Manager, Quality Control Manager or Hospital — plus their
geographical location. Hospital accounts additionally register the hospital name
and get a portal showing products issued to them.

## Download (ZIP)

- **This folder**: https://github.com/Sybers12/sybers12.github.io/raw/main/downloads/bloodbank.zip
- **OpenPACS**: https://github.com/Sybers12/sybers12.github.io/raw/main/downloads/pacs.zip
- Whole repository: https://github.com/Sybers12/sybers12.github.io/archive/refs/heads/main.zip

## Run locally (Linux)

```bash
git clone https://github.com/Sybers12/sybers12.github.io
cd sybers12.github.io/bloodbank

python3 -m venv ~/myenv          # or use your existing venv
source ~/myenv/bin/activate

pip install -r requirements.txt
python3 seed.py          # loads demo data (run once)
python3 run.py                   # serves on http://127.0.0.1:8500
```

Open **http://127.0.0.1:8500** in your browser.

## Demo accounts

All demo users use password **`demo123`**:

`admin`, `manager`, `quality`, `recruiter`, `head_donation`, `counselor`,
`head_lab`, `phlebotomist`, `lab_tech`, `data_clerk`, `council`
(the council user only sees approved results for *Ilala* council).

## Deploy online (free, Render)

The repo includes `render.yaml` at the root, so the Blood Bank can run as a live
website with a public URL:

1. Push the code to GitHub (already done) and go to
   [dashboard.render.com](https://dashboard.render.com) → **New + → Web Service**
2. Connect your GitHub account and pick the `Sybers12/sybers12.github.io` repo
   — Render reads `render.yaml` and fills in the settings automatically
3. Click **Apply** / **Create Web Service** and wait for the build
4. Your app gets a public URL like `https://nbts-bloodbank.onrender.com` —
   open it and sign in with a demo account

Notes:
- The free tier uses an ephemeral disk: demo data resets on each redeploy
  (the app re-seeds automatically). Use a paid plan or an external database
  for permanent storage.
- On first load the free service may sleep and take ~30s to wake up.

## Notes

- SMS sending is **simulated**: messages are logged to the database
  (`sms_logs` table) so the workflow can be demonstrated without an SMS
  gateway. Wire `POST /api/sms` to a real gateway (e.g. Africa's Talking)
  for production.
- The database is created at `bloodbank/data/bloodbank.db` (git-ignored).
- PDF reports are generated with ReportLab at
  `GET /api/pdf/results` and `GET /api/pdf/products`.
