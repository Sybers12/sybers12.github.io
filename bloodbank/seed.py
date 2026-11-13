import random
from datetime import date, timedelta

from database import SessionLocal, init_db
from models import (
    ABOD_GROUPS, BloodProduct, Donation, Donor, Hospital, PRODUCT_TYPES,
    SiteVisit, SmsLog, TestResult, User, hash_password, now_iso, today_str,
)

DISTRICTS = ["Ilala", "Kinondoni", "Temeke", "Ubungo", "Kigamboni", "Morogoro", "Arusha"]
COUNCILS = ["Ilala MC", "Kinondoni MC", "Temeke MC", "Ubungo MC", "Morogoro MC"]
VENUES = ["Muhimbili", "Makaburini", "Tegeta", "Uhasibu", "Mbezi", "Kariakoo", "University"]


def seed():
    init_db()
    with SessionLocal() as db:
        if db.query(User).count() > 0:
            print("Database already seeded; skipping.")
            return

        users = [
            ("admin", "ADMIN", "System Administrator", ""),
            ("manager", "MANAGER", "Anna Mwakalinga", ""),
            ("quality", "QUALITY", "Joseph Mrema", ""),
            ("recruiter", "RECRUITER", "Fatuma Ally", ""),
            ("head_donation", "HEAD_DONATION", "Peter Kalinga", ""),
            ("counselor", "COUNSELOR", "Grace Mollel", ""),
            ("head_lab", "HEAD_LAB", "Dr. Emmanuel Sengo", ""),
            ("phlebotomist", "PHLEBOTOMIST", "Neema Shirima", ""),
            ("lab_tech", "LAB_TECH", "Baraka Mtenga", ""),
            ("data_clerk", "DATA_CLERK", "Zawadi Nkya", ""),
            ("council", "COUNCIL", "Ilala Council Viewer", "Ilala"),
        ]
        for username, role, full_name, council in users:
            db.add(User(username=username, password=hash_password("demo123"),
                        full_name=full_name, role=role, council=council))

        hospitals = [
            ("Muhimbili National Hospital", "Dar es Salaam"),
            ("Aga Khan Hospital", "Dar es Salaam"),
            ("Temeke Regional Hospital", "Dar es Salaam"),
            ("Moro Regional Hospital", "Morogoro"),
            ("Mount Meru Hospital", "Arusha"),
        ]
        for name, region in hospitals:
            db.add(Hospital(name=name, region=region))
        db.flush()
        hospital_ids = [h.id for h in db.query(Hospital).all()]

        rng = random.Random(42)
        donors = []
        for i in range(40):
            last = date.today() - timedelta(days=rng.randint(10, 300))
            eligible = last + timedelta(days=90)
            district = rng.choice(DISTRICTS)
            donor = Donor(
                donor_no=f"DN-{i + 1:05d}",
                names=f"{rng.choice(['Juma', 'Asha', 'Baraka', 'Neema', 'David', 'Fatuma', 'Salma', 'John', 'Upendo', 'Rajabu'])} "
                      f"{rng.choice(['Mwinyi', 'Kimaro', 'Massawe', 'Chuwa', 'Mbwana', 'Ndosi', 'Mahenge', 'Swai'])} "
                      f"{rng.choice(['A.', 'B.', 'C.', 'D.'])}",
                birth_date=f"{rng.randint(1965, 2005)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                sex=rng.choice(["M", "F"]),
                phone=f"07{rng.randint(10, 99)}{rng.randint(100000, 999999)}",
                district=district,
                council=rng.choice(COUNCILS),
                times_donated=rng.randint(0, 12),
                last_donation_date=last.isoformat(),
                eligible_after=eligible.isoformat(),
            )
            donors.append(donor)
            db.add(donor)
        db.flush()

        donations = []
        for i in range(60):
            donor = rng.choice(donors)
            d = date.today() - timedelta(days=rng.randint(1, 120))
            donation = Donation(
                donation_no=f"DON-{23000 + i}",
                donor_id=donor.id, donation_date=d.isoformat(),
                venue=rng.choice(VENUES), district=donor.district,
                hemoglobin=round(rng.uniform(11.5, 17.0), 1),
                blood_pressure=f"{rng.randint(105, 135)}/{rng.randint(65, 88)}",
                volume_ml=450, phlebotomist="Neema Shirima",
            )
            donations.append(donation)
            db.add(donation)
        db.flush()

        products = []
        for i, donation in enumerate(donations):
            approved = i < 45
            reactive = 40 <= i < 45
            result = TestResult(
                donation_id=donation.id,
                abod=rng.choice(ABOD_GROUPS),
                hiv="POSITIVE" if reactive and rng.random() < 0.3 else "NEGATIVE",
                hbv="POSITIVE" if reactive and rng.random() < 0.3 else "NEGATIVE",
                hcv="NEGATIVE", syphilis="NEGATIVE",
                machine_ref=f"ABO-{rng.randint(1000, 9999)}",
                status="APPROVED" if approved else "REVIEWED",
                entered_by="Baraka Mtenga",
                approved_by="Dr. Emmanuel Sengo" if approved else "",
                approved_at=now_iso() if approved else "",
            )
            db.add(result)
            if approved and not reactive:
                for t in rng.sample(PRODUCT_TYPES, k=rng.randint(2, 4)):
                    seq = sum(1 for p in products if p.donation_id == donation.id and p.product_type == t)
                    status = rng.choice(["QUARANTINE", "READY", "READY", "ISSUED"])
                    product = BloodProduct(
                        product_code=f"{t}-{donation.donation_no}-{seq + 1}",
                        donation_id=donation.id, product_type=t, status=status,
                        labeled_by="Baraka Mtenga" if status != "QUARANTINE" else "",
                        labeled_at=now_iso() if status != "QUARANTINE" else "",
                        expiry_date=(date.today() + timedelta(
                            days={"PRC": 35, "FFP": 365, "PLT": 5, "CRYO": 365}[t])).isoformat(),
                    )
                    if status == "ISSUED":
                        product.hospital_id = rng.choice(hospital_ids)
                        product.issued_by = "Dr. Emmanuel Sengo"
                        product.issued_at = now_iso()
                    products.append(product)
                    db.add(product)
            elif i == 46:
                for t in ["PRC", "FFP"]:
                    product = BloodProduct(
                        product_code=f"{t}-{donation.donation_no}-1",
                        donation_id=donation.id, product_type=t,
                        status="QUARANTINE",
                        expiry_date=(date.today() + timedelta(
                            days={"PRC": 35, "FFP": 365, "PLT": 5, "CRYO": 365}[t])).isoformat(),
                    )
                    products.append(product)
                    db.add(product)

        for k in range(8):
            db.add(SiteVisit(
                venue=rng.choice(VENUES), district=rng.choice(DISTRICTS),
                visit_date=(date.today() + timedelta(days=rng.randint(-30, 30))).isoformat(),
                expected_donors=rng.randint(40, 150),
                actual_donors=rng.randint(30, 140) if k < 5 else 0,
                status="DONE" if k < 5 else "REQUESTED",
                requested_by="Fatuma Ally",
            ))
        for k in range(15):
            donor = rng.choice(donors)
            db.add(SmsLog(
                donor_id=donor.id, phone=donor.phone,
                message="Welcome back! Your deferral period is over - you can donate blood again. Thank you!",
                category="ELIGIBLE", sent_by="Fatuma Ally",
            ))
        db.commit()
        print(f"Seeded {len(donors)} donors, {len(donations)} donations, "
              f"{len(products)} products, {len(users)} users (password: demo123)")


if __name__ == "__main__":
    seed()
