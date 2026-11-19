from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator


class DietRequest(BaseModel):
    age :int=Field(ge=1,le=100)
    gender :Literal["male","female"]
    height :float=Field(gt=50,le=250,description="身高cm")
    weight :float =Field(gt=10,le=200,description="体重kg")
    allergies: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    daily_budget:float=Field(gt=0)
    goal :Literal["lose","maintain","gain"]

class DietRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:int
    status:Literal["pending","success","failed"]
    final_plan:dict|None
    retry_count:int
    review_feedback:str|None
    created_at:datetime

class Ingredient(BaseModel):
    name:str=Field(description="食材名字")
    amount_g:float=Field(gt=0,description="用量，单位g")


class Dish(BaseModel):
    name:str=Field(min_length=1)
    ingredients:list[Ingredient]=Field(min_length=1)

class Meal(BaseModel):
    name:Literal["早餐","午餐","晚餐"]
    dishes:list[Dish]=Field(min_length=1)

class DietPlan(BaseModel):
    meals:list[Meal]=Field(min_length=1)
    notes :str=""


class QualityIssue(BaseModel):
    category: Literal[
        "meal_structure",
        "ingredient_pairing",
        "portion",
        "cooking",
        "variety",
        "goal_alignment",
        "other",
    ]
    severity: Literal["blocking", "major", "minor"]
    evidence: str = Field(min_length=1, description="具体餐次、菜品或食材依据")
    suggestion: str = Field(min_length=1, description="可执行的修改建议")


class JudgeVerdict(BaseModel):
    approved: bool
    score: int = Field(ge=0, le=100)
    issues: list[QualityIssue] = Field(default_factory=list)
    summary: str = ""

    @model_validator(mode="after")
    def check_decision_consistency(self) -> "JudgeVerdict":
        has_blocking = any(
            issue.severity == "blocking" for issue in self.issues
        )
        if self.approved and has_blocking:
            raise ValueError("存在 blocking 问题时不能批准食谱")
        if not self.approved and not has_blocking:
            raise ValueError("否决食谱时必须至少给出一个 blocking 问题")
        return self

