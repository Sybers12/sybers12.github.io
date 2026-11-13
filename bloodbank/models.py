import hashlib
import secrets
from datetime import date, datetime, timezone

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

ROLES = [
    "ADMIN", "MANAGER", "QUALITY", "RECRUITER", "HEAD_DONATION", "COUNSELOR",
    "HEAD_LAB", "PHLEBOTOMIST", "LAB_TECH", "DATA_CLERK", "COUNCIL", "HOSPITAL",
]

REGISTER_CATEGORIES = ["ADMIN", "MANAGER", "QUALITY", "HOSPITAL"]

PRODUCT_TYPES = ["PRC", "FFP", "PLT", "CRYO"]
RESULT_VALUES = ["NEGATIVE", "POSITIVE"]
ABOD_GROUPS = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str() -> str:
    return date.today().isoformat()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(32), index=True)
    council: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(96), default="")
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)

    hospital: Mapped["Hospital | None"] = relationship()


class Token(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    user: Mapped["User"] = relationship()


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_no: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    names: Mapped[str] = mapped_column(String(192), index=True)
    birth_date: Mapped[str] = mapped_column(String(10), default="")
    sex: Mapped[str] = mapped_column(String(1), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    district: Mapped[str] = mapped_column(String(64), default="", index=True)
    council: Mapped[str] = mapped_column(String(64), default="")
    times_donated: Mapped[int] = mapped_column(Integer, default=0)
    last_donation_date: Mapped[str] = mapped_column(String(10), default="")
    eligible_after: Mapped[str] = mapped_column(String(10), default="")
    registered_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    donations: Mapped[list["Donation"]] = relationship(back_populates="donor")


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(primary_key=True)
    donation_no: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    donation_date: Mapped[str] = mapped_column(String(10), default=today_str, index=True)
    venue: Mapped[str] = mapped_column(String(128), default="")
    district: Mapped[str] = mapped_column(String(64), default="")
    hemoglobin: Mapped[float] = mapped_column(default=0.0)
    blood_pressure: Mapped[str] = mapped_column(String(16), default="")
    volume_ml: Mapped[int] = mapped_column(Integer, default=450)
    phlebotomist: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="COLLECTED", index=True)

    donor: Mapped["Donor"] = relationship(back_populates="donations")
    result: Mapped["TestResult | None"] = relationship(back_populates="donation")


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    donation_id: Mapped[int] = mapped_column(ForeignKey("donations.id"), unique=True)
    abod: Mapped[str] = mapped_column(String(4), default="")
    hiv: Mapped[str] = mapped_column(String(16), default="")
    hbv: Mapped[str] = mapped_column(String(16), default="")
    hcv: Mapped[str] = mapped_column(String(16), default="")
    syphilis: Mapped[str] = mapped_column(String(16), default="")
    machine_ref: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="REVIEWED", index=True)
    entered_by: Mapped[str] = mapped_column(String(128), default="")
    entered_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    approved_at: Mapped[str] = mapped_column(String(32), default="")

    donation: Mapped["Donation"] = relationship(back_populates="result")


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    region: Mapped[str] = mapped_column(String(64), default="")


class BloodProduct(Base):
    __tablename__ = "blood_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    donation_id: Mapped[int] = mapped_column(ForeignKey("donations.id"))
    product_type: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16), default="QUARANTINE", index=True)
    labeled_by: Mapped[str] = mapped_column(String(128), default="")
    labeled_at: Mapped[str] = mapped_column(String(32), default="")
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    issued_by: Mapped[str] = mapped_column(String(128), default="")
    issued_at: Mapped[str] = mapped_column(String(32), default="")
    expiry_date: Mapped[str] = mapped_column(String(10), default="")

    donation: Mapped["Donation"] = relationship()
    hospital: Mapped["Hospital | None"] = relationship()


class SiteVisit(Base):
    __tablename__ = "site_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue: Mapped[str] = mapped_column(String(128))
    district: Mapped[str] = mapped_column(String(64), default="", index=True)
    visit_date: Mapped[str] = mapped_column(String(10), index=True)
    expected_donors: Mapped[int] = mapped_column(Integer, default=0)
    actual_donors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="REQUESTED", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    phone: Mapped[str] = mapped_column(String(20), default="")
    message: Mapped[str] = mapped_column(String(320))
    category: Mapped[str] = mapped_column(String(32), default="GENERAL", index=True)
    sent_by: Mapped[str] = mapped_column(String(128), default="")
    sent_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    donor: Mapped["Donor"] = relationship()
