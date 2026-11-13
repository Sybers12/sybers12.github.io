from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db():
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _migrate(engine)


def _migrate(engine):
    """Add columns introduced after the first release to existing databases."""
    wanted = {
        "users": {
            "location": "VARCHAR(96) DEFAULT ''",
            "hospital_id": "INTEGER",
            "council": "VARCHAR(64) DEFAULT ''",
        },
    }
    with engine.connect() as conn:
        for table, columns in wanted.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            if not existing:
                continue
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        conn.commit()
