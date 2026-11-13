from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(192), index=True)
    birth_date: Mapped[str] = mapped_column(String(8), default="")
    sex: Mapped[str] = mapped_column(String(1), default="")

    studies: Mapped[list["Study"]] = relationship(back_populates="patient")


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_pk: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    study_date: Mapped[str] = mapped_column(String(8), default="", index=True)
    study_time: Mapped[str] = mapped_column(String(16), default="")
    modality: Mapped[str] = mapped_column(String(16), default="", index=True)
    description: Mapped[str] = mapped_column(String(64), default="")
    accession_number: Mapped[str] = mapped_column(String(32), default="", index=True)
    referring_physician: Mapped[str] = mapped_column(String(192), default="")
    created_at: Mapped[str] = mapped_column(
        String(32),
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )

    patient: Mapped["Patient"] = relationship(back_populates="studies")
    series: Mapped[list["Series"]] = relationship(back_populates="study")


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    study_pk: Mapped[int] = mapped_column(ForeignKey("studies.id"))
    modality: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(String(64), default="")
    series_number: Mapped[int] = mapped_column(Integer, default=0)
    body_part: Mapped[str] = mapped_column(String(64), default="")

    study: Mapped["Study"] = relationship(back_populates="series")
    instances: Mapped[list["Instance"]] = relationship(back_populates="series")


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    sop_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    series_pk: Mapped[int] = mapped_column(ForeignKey("series.id"))
    instance_number: Mapped[int] = mapped_column(Integer, default=1)
    file_path: Mapped[str] = mapped_column(String(512))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    cols: Mapped[int] = mapped_column(Integer, default=0)
    number_of_frames: Mapped[int] = mapped_column(Integer, default=1)
    window_center: Mapped[float] = mapped_column(Float, default=0.0)
    window_width: Mapped[float] = mapped_column(Float, default=0.0)
    pixel_spacing_x: Mapped[float] = mapped_column(Float, default=1.0)
    pixel_spacing_y: Mapped[float] = mapped_column(Float, default=1.0)
    slice_thickness: Mapped[float] = mapped_column(Float, default=1.0)
    rescale_slope: Mapped[float] = mapped_column(Float, default=1.0)
    rescale_intercept: Mapped[float] = mapped_column(Float, default=0.0)
    photometric: Mapped[str] = mapped_column(String(16), default="MONOCHROME2")

    series: Mapped["Series"] = relationship(back_populates="instances")
