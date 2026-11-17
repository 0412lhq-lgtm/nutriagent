from app.database import Base, engine
import app.models  # noqa: F401  导入即登记，必须放在 create_all 之前

Base.metadata.create_all(bind=engine)
print("建表完成：", Base.metadata.tables.keys())