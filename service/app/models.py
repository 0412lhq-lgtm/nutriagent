from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime, func, Text
from sqlalchemy.orm import  Mapped, mapped_column
from app.database import Base


class DietRecord(Base):
    __tablename__ = "diet_records"          # 数据库里的表名

    id: Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    request_data: Mapped[dict] = mapped_column(JSON)
    final_plan: Mapped[dict|None] = mapped_column(JSON,nullable=True)
    review_feedback:Mapped[str|None]=mapped_column(Text,nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer,default=0)
    status:Mapped[str]=mapped_column(String(20),default="pending")
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())