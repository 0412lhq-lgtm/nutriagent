from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


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

