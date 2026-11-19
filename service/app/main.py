from contextlib import asynccontextmanager
from fastapi import Request
from fastapi.responses import JSONResponse
from app.agent.llm import PlanGenerationError
import uvicorn
from app.agent.tools import decorate_plan
from app.schemas import DietRecordOut,DietRequest
from app.models import DietRecord
from starlette.middleware.cors import CORSMiddleware
from app.agent.graph import build_graph
from app.database import Base,engine,SessionLocal
from fastapi import FastAPI, HTTPException
from app.config import settings


@asynccontextmanager
async def lifespan(_:FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

api=FastAPI(title="NutriAgent",lifespan=lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 允许任何源访问
    allow_methods=["*"],          # 允许 GET/POST/PUT/DELETE 等所有方法
    allow_headers=["*"],          # 允许 Authorization 等自定义请求头
)


@api.exception_handler(PlanGenerationError)
async def plan_generation_error_handler(_: Request, exc: PlanGenerationError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})
graph=build_graph()

@api.get("/health")
def health():
    return {"status":"ok"}

@api.post("/api/diet-plans", response_model=DietRecordOut)
def create_diet_plan(request: DietRequest):
    result = graph.invoke(
        {
            "request": request,
            "plan": None,
            "violations": [],
            "retry_count": 0,
            "max_retries": settings.agent.max,
            "status": "pending",
            "quality_verdict": None,
            "quality_feedback": [],
            "bmi": None,
            "bmr": None,
            "infeasible_reason": None,
        }
    )

    # 预算不可行：不生成、不入库，直接告诉客户端
    if result.get("infeasible_reason"):
        raise HTTPException(status_code=422, detail=result["infeasible_reason"])

    plan = result["plan"]
    feedback = result["violations"] + result.get("quality_feedback", [])
    record = DietRecord(
        request_data=request.model_dump(),
        final_plan=decorate_plan(plan) if result["status"] == "success" and plan else None,
        review_feedback="\n".join(feedback) or None,
        retry_count=result["retry_count"],
        status=result["status"],
    )

    db = SessionLocal()
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    finally:
        db.close()

    return record


@api.get("/api/diet-plans/{record_id}",response_model=DietRecordOut)
def get_diet_plan(record_id:int):
    db=SessionLocal()
    try:
        record=db.get(DietRecord,record_id)
    finally:
        db.close()
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record

if __name__ == '__main__':
    uvicorn.run(
        "app.main:api",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )