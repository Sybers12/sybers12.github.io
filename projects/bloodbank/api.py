import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    ABOD_GROUPS, BloodProduct, Donation, Donor, Hospital, PRODUCT_TYPES,
    REGISTER_CATEGORIES, RESULT_VALUES, ROLES, SiteVisit, SmsLog, TestResult,
    Token, User, hash_password, now_iso, today_str, verify_password,
)
from auth import ROLE_PERMISSIONS, ensure_permission, get_current_user, get_db

router = APIRouter(prefix="/api")

APPROVERS = {"HEAD_LAB", "QUALITY", "MANAGER"}
DONOR_WRITERS = {"DATA_CLERK", "HEAD_DONATION", "MANAGER", "COUNSELOR"}
DONATION_WRITERS = {"PHLEBOTOMIST", "DATA_CLERK", "HEAD_DONATION", "MANAGER"}
LAB_WRITERS = {"LAB_TECH", "HEAD_LAB", "QUALITY", "MANAGER"}
PRODUCT_WRITERS = {"LAB_TECH", "HEAD_LAB", "MANAGER"}
SHELF_LIFE = {"PRC": 35, "FFP": 365, "PLT": 5, "CRYO": 365}


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    full_name: str = ""
    category: str
    location: str = ""
    hospital_name: str = ""


class DonorIn(BaseModel):
    names: str
    birth_date: str = ""
    sex: str = ""
    phone: str = ""
    district: str = ""
    council: str = ""


class DonationIn(BaseModel):
    donor_id: int
    venue: str = ""
    district: str = ""
    hemoglobin: float = 0.0
    blood_pressure: str = ""
    volume_ml: int = 450


class ResultIn(BaseModel):
    donation_id: int
    abod: str
    hiv: str = "NEGATIVE"
    hbv: str = "NEGATIVE"
    hcv: str = "NEGATIVE"
    syphilis: str = "NEGATIVE"
    machine_ref: str = ""
    notes: str = ""


class ProductSortIn(BaseModel):
    donation_id: int
    types: list[str]


class IssueIn(BaseModel):
    hospital_id: int


class VisitIn(BaseModel):
    venue: str
    district: str = ""
    visit_date: str
    expected_donors: int = 0


class SmsIn(BaseModel):
    donor_ids: list[int] | None = None
    target: str = "ELIGIBLE"
    message: str


def _donor_dict(d: Donor) -> dict:
    return {
        "id": d.id, "donor_no": d.donor_no, "names": d.names,
        "birth_date": d.birth_date, "sex": d.sex, "phone": d.phone,
        "district": d.district, "council": d.council,
        "times_donated": d.times_donated, "last_donation_date": d.last_donation_date,
        "eligible_after": d.eligible_after,
        "eligible": (not d.eligible_after) or d.eligible_after <= today_str(),
    }


def _donation_dict(d: Donation, with_donor: bool = True) -> dict:
    out = {
        "id": d.id, "donation_no": d.donation_no, "donor_id": d.donor_id,
        "donation_date": d.donation_date, "venue": d.venue, "district": d.district,
        "hemoglobin": d.hemoglobin, "blood_pressure": d.blood_pressure,
        "volume_ml": d.volume_ml, "phlebotomist": d.phlebotomist, "status": d.status,
    }
    if with_donor and d.donor:
        out["donor_no"] = d.donor.donor_no
        out["donor_names"] = d.donor.names
    if d.result:
        r = d.result
        out["result"] = {
            "id": r.id, "abod": r.abod, "hiv": r.hiv, "hbv": r.hbv,
            "hcv": r.hcv, "syphilis": r.syphilis, "machine_ref": r.machine_ref,
            "notes": r.notes, "status": r.status, "approved_by": r.approved_by,
        }
    return out


def _product_dict(p: BloodProduct) -> dict:
    return {
        "id": p.id, "product_code": p.product_code, "product_type": p.product_type,
        "status": p.status, "expiry_date": p.expiry_date,
        "donation_no": p.donation.donation_no if p.donation else "",
        "donor_no": p.donation.donor.donor_no if p.donation and p.donation.donor else "",
        "abod": p.donation.result.abod if p.donation and p.donation.result else "",
        "safe": bool(
            p.donation and p.donation.result
            and p.donation.result.status == "APPROVED"
            and p.donation.result.hiv == "NEGATIVE"
            and p.donation.result.hbv == "NEGATIVE"
            and p.donation.result.hcv == "NEGATIVE"
            and p.donation.result.syphilis == "NEGATIVE"
        ),
        "hospital": p.hospital.name if p.hospital else "",
        "issued_by": p.issued_by, "issued_at": p.issued_at,
    }


def _next_no(db, model, column, prefix) -> str:
    count = db.query(model).count()
    return f"{prefix}-{count + 1:05d}"


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).one_or_none()
    if user is None or not verify_password(body.password, user.password):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_hex(16)
    db.add(Token(token=token, user_id=user.id))
    db.commit()
    return {"token": token, "role": user.role, "full_name": user.full_name,
            "council": user.council}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    category = body.category.strip().upper()
    if category not in REGISTER_CATEGORIES:
        raise HTTPException(400, "Invalid category. Choose: " + ", ".join(REGISTER_CATEGORIES))
    username = body.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(body.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    if db.query(User).filter_by(username=username).one_or_none():
        raise HTTPException(400, "Username already taken")

    hospital_id = None
    if category == "HOSPITAL":
        hospital_name = body.hospital_name.strip()
        if not hospital_name:
            raise HTTPException(400, "Hospital name is required for the Hospital category")
        hospital = db.query(Hospital).filter_by(name=hospital_name).one_or_none()
        if hospital is None:
            hospital = Hospital(name=hospital_name, region=body.location.strip())
            db.add(hospital)
            db.flush()
        hospital_id = hospital.id

    user = User(
        username=username, password=hash_password(body.password),
        full_name=body.full_name.strip() or username,
        role=category, location=body.location.strip(), hospital_id=hospital_id,
    )
    db.add(user)
    db.commit()

    token = secrets.token_hex(16)
    db.add(Token(token=token, user_id=user.id))
    db.commit()
    return {"token": token, "role": user.role, "full_name": user.full_name,
            "council": user.council, "location": user.location}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"username": user.username, "role": user.role,
            "full_name": user.full_name, "council": user.council,
            "location": user.location,
            "hospital": user.hospital.name if user.hospital else ""}


@router.post("/logout")
def logout(user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Token).filter_by(user_id=user.id).delete()
    db.commit()
    return {"ok": True}


# ---------------- Donors ----------------

@router.get("/donors")
def list_donors(search: str = "", user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "donors")
    q = db.query(Donor)
    if search:
        like = f"%{search}%"
        q = q.filter((Donor.names.ilike(like)) | (Donor.donor_no.ilike(like)) | (Donor.phone.ilike(like)))
    return [_donor_dict(d) for d in q.order_by(Donor.id.desc()).limit(500)]


@router.post("/donors")
def create_donor(body: DonorIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "donors")
    donor = Donor(
        donor_no=_next_no(db, Donor, Donor.donor_no, "DN"),
        names=body.names.strip(), birth_date=body.birth_date, sex=body.sex,
        phone=body.phone, district=body.district, council=body.council,
    )
    db.add(donor)
    db.commit()
    return _donor_dict(donor)


@router.get("/donors/{donor_id}")
def donor_detail(donor_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "donors")
    donor = db.query(Donor).get((donor_id,))
    if donor is None:
        raise HTTPException(404, "Donor not found")
    donations = (
        db.query(Donation).filter_by(donor_id=donor.id)
        .order_by(Donation.donation_date.desc()).all()
    )
    return {"donor": _donor_dict(donor),
            "donations": [_donation_dict(d, with_donor=False) for d in donations]}


# ---------------- Donations ----------------

@router.get("/donations")
def list_donations(donor_id: int | None = None, date_from: str = "", date_to: str = "",
                   user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "donations")
    q = db.query(Donation)
    if donor_id:
        q = q.filter_by(donor_id=donor_id)
    if date_from:
        q = q.filter(Donation.donation_date >= date_from)
    if date_to:
        q = q.filter(Donation.donation_date <= date_to)
    return [_donation_dict(d) for d in q.order_by(Donation.id.desc()).limit(500)]


@router.post("/donations")
def create_donation(body: DonationIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "donations")
    donor = db.query(Donor).get((body.donor_id,))
    if donor is None:
        raise HTTPException(404, "Donor not found")
    if donor.eligible_after and donor.eligible_after > today_str():
        raise HTTPException(400, f"Donor not eligible until {donor.eligible_after}")
    donation = Donation(
        donation_no=_next_no(db, Donation, Donation.donation_no, "DON"),
        donor_id=donor.id, venue=body.venue, district=body.district or donor.district,
        hemoglobin=body.hemoglobin, blood_pressure=body.blood_pressure,
        volume_ml=body.volume_ml, phlebotomist=user.full_name,
    )
    donor.times_donated += 1
    donor.last_donation_date = today_str()
    donor.eligible_after = (date.today() + timedelta(days=90)).isoformat()
    db.add(donation)
    db.commit()
    return _donation_dict(donation)


# ---------------- Recruiting: site visits + SMS ----------------

@router.get("/visits")
def list_visits(status: str = "", user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    q = db.query(SiteVisit)
    if status:
        q = q.filter_by(status=status)
    visits = q.order_by(SiteVisit.visit_date.desc()).limit(300)
    return [{
        "id": v.id, "venue": v.venue, "district": v.district, "visit_date": v.visit_date,
        "expected_donors": v.expected_donors, "actual_donors": v.actual_donors,
        "status": v.status, "requested_by": v.requested_by,
    } for v in visits]


@router.post("/visits")
def create_visit(body: VisitIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    visit = SiteVisit(venue=body.venue, district=body.district,
                      visit_date=body.visit_date, expected_donors=body.expected_donors,
                      requested_by=user.full_name)
    db.add(visit)
    db.commit()
    return {"id": visit.id, "status": visit.status}


@router.post("/visits/{visit_id}/complete")
def complete_visit(visit_id: int, actual_donors: int = 0,
                   user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    visit = db.query(SiteVisit).get((visit_id,))
    if visit is None:
        raise HTTPException(404, "Visit not found")
    visit.actual_donors = actual_donors
    visit.status = "DONE"
    db.commit()
    return {"id": visit.id, "status": visit.status}


@router.post("/sms")
def send_sms(body: SmsIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    if body.donor_ids:
        donors = db.query(Donor).filter(Donor.id.in_(body.donor_ids)).all()
    elif body.target == "ELIGIBLE":
        donors = db.query(Donor).filter(
            (Donor.eligible_after == "") | (Donor.eligible_after <= today_str())
        ).all()
    else:
        donors = db.query(Donor).all()
    sent = 0
    for donor in donors:
        if not donor.phone:
            continue
        db.add(SmsLog(donor_id=donor.id, phone=donor.phone, message=body.message,
                      category=body.target, sent_by=user.full_name))
        sent += 1
    db.commit()
    return {"sent": sent}


@router.get("/sms")
def list_sms(user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    logs = db.query(SmsLog).order_by(SmsLog.id.desc()).limit(200)
    return [{
        "id": s.id, "donor": s.donor.names if s.donor else "", "phone": s.phone,
        "message": s.message, "category": s.category, "sent_by": s.sent_by,
        "sent_at": s.sent_at,
    } for s in logs]


@router.get("/recruiter/stats")
def recruiter_stats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "recruiting")
    by_area = dict(
        db.query(Donation.venue, func.count(Donation.id))
        .group_by(Donation.venue).all()
    )
    visits = db.query(SiteVisit).all()
    return {
        "donations_by_area": by_area,
        "visits": {
            "total": len(visits),
            "requested": sum(1 for v in visits if v.status == "REQUESTED"),
            "done": sum(1 for v in visits if v.status == "DONE"),
            "actual_donors": sum(v.actual_donors for v in visits),
        },
    }


# ---------------- Laboratory ----------------

@router.get("/lab/pending")
def lab_pending(user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "lab")
    rows = (
        db.query(Donation).outerjoin(TestResult, Donation.id == TestResult.donation_id)
        .filter(TestResult.id.is_(None))
        .order_by(Donation.id).limit(300)
    )
    return [_donation_dict(d) for d in rows]


@router.post("/lab/results")
def enter_result(body: ResultIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "lab")
    if body.abod not in ABOD_GROUPS:
        raise HTTPException(400, "Invalid blood group")
    for field in ("hiv", "hbv", "hcv", "syphilis"):
        value = getattr(body, field).upper()
        if value not in RESULT_VALUES:
            raise HTTPException(400, f"{field.upper()} value must be NEGATIVE or POSITIVE")
    donation = db.query(Donation).get((body.donation_id,))
    if donation is None:
        raise HTTPException(404, "Donation not found")
    existing = db.query(TestResult).filter_by(donation_id=donation.id).one_or_none()
    if existing:
        raise HTTPException(400, "Result already entered")
    result = TestResult(
        donation_id=donation.id, abod=body.abod,
        hiv=body.hiv.upper(), hbv=body.hbv.upper(),
        hcv=body.hcv.upper(), syphilis=body.syphilis.upper(),
        machine_ref=body.machine_ref, notes=body.notes,
        status="REVIEWED", entered_by=user.full_name,
    )
    reactive = any(getattr(result, f) == "POSITIVE" for f in ("hiv", "hbv", "hcv", "syphilis"))
    if reactive:
        result.status = "DISCREPANCY"
    db.add(result)
    db.commit()
    return _donation_dict(donation)


@router.put("/lab/results/{result_id}")
def edit_result(result_id: int, body: ResultIn, user=Depends(get_current_user),
                db: Session = Depends(get_db)):
    ensure_permission(user, "lab")
    result = db.query(TestResult).get((result_id,))
    if result is None:
        raise HTTPException(404, "Result not found")
    if result.status == "APPROVED" and user.role not in APPROVERS:
        raise HTTPException(403, "Approved results need approver rights")
    result.abod = body.abod
    result.hiv = body.hiv.upper()
    result.hbv = body.hbv.upper()
    result.hcv = body.hcv.upper()
    result.syphilis = body.syphilis.upper()
    result.machine_ref = body.machine_ref
    result.notes = body.notes
    result.status = "DISCREPANCY" if result.status == "APPROVED" else "REVIEWED"
    reactive = any(getattr(result, f) == "POSITIVE" for f in ("hiv", "hbv", "hcv", "syphilis"))
    if reactive:
        result.status = "DISCREPANCY"
    result.entered_by = user.full_name
    result.entered_at = now_iso()
    db.commit()
    return _donation_dict(result.donation)


@router.post("/lab/results/{result_id}/approve")
def approve_result(result_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "lab")
    if user.role not in APPROVERS:
        raise HTTPException(403, "Only approvers can approve")
    result = db.query(TestResult).get((result_id,))
    if result is None:
        raise HTTPException(404, "Result not found")
    if result.status == "DISCREPANCY":
        raise HTTPException(400, "Resolve discrepancy first")
    result.status = "APPROVED"
    result.approved_by = user.full_name
    result.approved_at = now_iso()
    db.commit()
    return _donation_dict(result.donation)


@router.get("/lab/results")
def list_results(status: str = "", no_from: int | None = None, no_to: int | None = None,
                 abod: str = "", tti: str = "",
                 user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "lab")
    q = db.query(TestResult).join(Donation, TestResult.donation_id == Donation.id)
    if status:
        q = q.filter(TestResult.status == status)
    if no_from is not None:
        q = q.filter(Donation.donation_no >= f"DON-{no_from:05d}")
    if no_to is not None:
        q = q.filter(Donation.donation_no <= f"DON-{no_to:05d}")
    if abod:
        q = q.filter(TestResult.abod == abod)
    if tti == "REACTIVE":
        q = q.filter((TestResult.hiv == "POSITIVE") | (TestResult.hbv == "POSITIVE") |
                     (TestResult.hcv == "POSITIVE") | (TestResult.syphilis == "POSITIVE"))
    elif tti == "NON_REACTIVE":
        q = q.filter((TestResult.hiv == "NEGATIVE") & (TestResult.hbv == "NEGATIVE") &
                     (TestResult.hcv == "NEGATIVE") & (TestResult.syphilis == "NEGATIVE"))
    rows = q.order_by(Donation.donation_no.desc()).limit(500)
    return [_donation_dict(r.donation) for r in rows]


# ---------------- Products ----------------

@router.post("/products/sort")
def sort_products(body: ProductSortIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "products")
    for t in body.types:
        if t not in PRODUCT_TYPES:
            raise HTTPException(400, f"Unknown product type {t}")
    donation = db.query(Donation).get((body.donation_id,))
    if donation is None:
        raise HTTPException(404, "Donation not found")
    created = []
    for t in body.types:
        seq = db.query(BloodProduct).filter_by(donation_id=donation.id, product_type=t).count()
        product = BloodProduct(
            product_code=f"{t}-{donation.donation_no}-{seq + 1}",
            donation_id=donation.id, product_type=t,
            expiry_date=(date.today() + timedelta(days=SHELF_LIFE[t])).isoformat(),
        )
        db.add(product)
        created.append(product)
    db.commit()
    return [_product_dict(p) for p in created]


@router.get("/products")
def list_products(product_type: str = "", status: str = "", hospital_id: int | None = None,
                  user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "products")
    q = db.query(BloodProduct)
    if product_type:
        q = q.filter_by(product_type=product_type)
    if status:
        q = q.filter_by(status=status)
    if hospital_id:
        q = q.filter_by(hospital_id=hospital_id)
    return [_product_dict(p) for p in q.order_by(BloodProduct.id.desc()).limit(500)]


@router.post("/products/{product_id}/label")
def label_product(product_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "products")
    product = db.query(BloodProduct).get((product_id,))
    if product is None:
        raise HTTPException(404, "Product not found")
    if product.status != "QUARANTINE":
        raise HTTPException(400, "Product already labeled")
    product.status = "READY"
    product.labeled_by = user.full_name
    product.labeled_at = now_iso()
    db.commit()
    return _product_dict(product)


@router.post("/products/{product_id}/issue")
def issue_product(product_id: int, body: IssueIn, user=Depends(get_current_user),
                  db: Session = Depends(get_db)):
    ensure_permission(user, "products")
    product = db.query(BloodProduct).get((product_id,))
    if product is None:
        raise HTTPException(404, "Product not found")
    if product.status != "READY":
        raise HTTPException(400, "Label before issuing")
    result = product.donation.result if product.donation else None
    if result is None or result.status != "APPROVED":
        raise HTTPException(400, "Results not approved")
    if any(getattr(result, f) == "POSITIVE" for f in ("hiv", "hbv", "hcv", "syphilis")):
        raise HTTPException(400, "Blood is reactive — cannot issue")
    hospital = db.query(Hospital).get((body.hospital_id,))
    if hospital is None:
        raise HTTPException(404, "Hospital not found")
    product.status = "ISSUED"
    product.hospital_id = hospital.id
    product.issued_by = user.full_name
    product.issued_at = now_iso()
    db.commit()
    return _product_dict(product)


@router.get("/hospitals")
def list_hospitals(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": h.id, "name": h.name, "region": h.region}
            for h in db.query(Hospital).order_by(Hospital.name)]


# ---------------- Council (view-only approved) ----------------

@router.get("/council/results")
def council_results(user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "council")
    q = (
        db.query(TestResult).filter(TestResult.status == "APPROVED")
        .join(Donation, TestResult.donation_id == Donation.id)
    )
    if user.council:
        q = q.filter(Donation.district == user.council)
    rows = q.order_by(Donation.donation_no.desc()).limit(500)
    return [_donation_dict(r.donation) for r in rows]


# ---------------- Hospital portal ----------------

@router.get("/hospital/portal")
def hospital_portal(user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "hospital_portal")
    hospital = user.hospital
    if hospital is None:
        return {"hospital": {"name": user.full_name, "region": user.location},
                "summary": {}, "products": []}
    rows = (
        db.query(BloodProduct).filter_by(hospital_id=hospital.id)
        .order_by(BloodProduct.id.desc()).limit(300)
    )
    products = [_product_dict(p) for p in rows]
    summary = {
        "total": len(products),
        "by_type": {},
    }
    for p in products:
        summary["by_type"][p["product_type"]] = summary["by_type"].get(p["product_type"], 0) + 1
    return {
        "hospital": {"name": hospital.name, "region": hospital.region},
        "summary": summary,
        "products": products,
    }


# ---------------- Statistics ----------------

@router.get("/stats")
def stats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if "stats" not in ROLE_PERMISSIONS.get(user.role, set()) and user.role != "COUNCIL":
        raise HTTPException(403, "Permission denied")
    total_donors = db.query(Donor).count()
    total_donations = db.query(Donation).count()

    groups = dict(
        db.query(TestResult.abod, func.count(TestResult.id))
        .filter(TestResult.abod != "").group_by(TestResult.abod).all()
    )
    group_pct = {
        g: {"count": c, "pct": round(c * 100.0 / max(1, sum(groups.values())), 1)}
        for g, c in groups.items()
    }

    reactive = {
        f: db.query(TestResult).filter(getattr(TestResult, f) == "POSITIVE").count()
        for f in ("hiv", "hbv", "hcv", "syphilis")
    }
    tested = db.query(TestResult).count()

    products = dict(
        db.query(BloodProduct.status, func.count(BloodProduct.id))
        .group_by(BloodProduct.status).all()
    )
    by_type = dict(
        db.query(BloodProduct.product_type, func.count(BloodProduct.id))
        .group_by(BloodProduct.product_type).all()
    )
    issued_by_hospital = dict(
        db.query(Hospital.name, func.count(BloodProduct.id))
        .join(BloodProduct, BloodProduct.hospital_id == Hospital.id)
        .group_by(Hospital.name).all()
    )
    eligible = db.query(Donor).filter(
        (Donor.eligible_after == "") | (Donor.eligible_after <= today_str())
    ).count()

    return {
        "donors": {"total": total_donors, "eligible": eligible},
        "donations": {"total": total_donations},
        "blood_groups": group_pct,
        "tti": {"tested": tested, **reactive,
                "reactive_pct": round(sum(reactive.values()) * 100.0 / max(1, tested), 1)},
        "products": {"by_status": products, "by_type": by_type,
                     "issued_by_hospital": issued_by_hospital},
    }
