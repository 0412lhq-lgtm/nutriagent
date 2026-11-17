from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
class Base(DeclarativeBase):
    pass
DATABASE_URL = (
    f"mysql+pymysql://{quote_plus(settings.db.user)}:{quote_plus(settings.db.password)}"
    f"@{settings.db.host}:{settings.db.port}/{settings.db.db}"
    f"?charset=utf8mb4"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)