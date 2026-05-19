from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_initial_users(db):
    """Bootstrap the admin user on a fresh database and ensure every user has
    a user_profiles row."""
    import bcrypt

    existing = db.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
    if not existing:
        hashed = bcrypt.hashpw(
            settings.default_admin_password.encode("utf-8"), bcrypt.gensalt(12)
        ).decode("utf-8")
        db.execute(
            text(
                "INSERT INTO users (username, password_hash, force_password_change, role, is_active) "
                "VALUES (:u, :h, true, 'admin', true)"
            ),
            {"u": settings.default_admin_username, "h": hashed},
        )
        db.commit()

    db.execute(text(
        "INSERT INTO user_profiles (user_id) "
        "SELECT id FROM users "
        "WHERE id NOT IN (SELECT user_id FROM user_profiles)"
    ))
    db.commit()
