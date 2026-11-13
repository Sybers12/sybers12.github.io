from fastapi import Depends, Header, HTTPException, Query

from ..database import SessionLocal
from ..models import ROLES, Token, User

ROLE_PERMISSIONS = {
    "ADMIN": {"donors", "donations", "recruiting", "lab", "products", "stats", "pdf", "council", "hospital_portal"},
    "HOSPITAL": {"hospital_portal", "stats"},
    "MANAGER": {"donors", "donations", "recruiting", "lab", "products", "stats", "pdf"},
    "QUALITY": {"lab", "products", "stats", "pdf"},
    "RECRUITER": {"recruiting", "stats"},
    "HEAD_DONATION": {"donors", "donations", "recruiting", "stats"},
    "COUNSELOR": {"donors", "donations", "stats"},
    "HEAD_LAB": {"lab", "products", "stats", "pdf"},
    "PHLEBOTOMIST": {"donations", "stats"},
    "LAB_TECH": {"lab", "products", "stats", "pdf"},
    "DATA_CLERK": {"donors", "donations", "stats"},
    "COUNCIL": {"council"},
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str = Header(default=""),
                     token: str = Query(default=""), db=Depends(get_db)) -> User:
    value = token or authorization.replace("Bearer ", "").strip()
    if not value:
        raise HTTPException(401, "Not logged in")
    row = db.query(Token).filter_by(token=value).one_or_none()
    if row is None:
        raise HTTPException(401, "Invalid token")
    return db.query(User).filter_by(id=row.user_id).one()


def require_role(user: User = Depends(get_current_user)):
    return user


def has_permission(user: User, section: str) -> bool:
    return section in ROLE_PERMISSIONS.get(user.role, set())


def ensure_permission(user: User, section: str):
    if not has_permission(user, section):
        raise HTTPException(403, f"Permission denied for {section}")
