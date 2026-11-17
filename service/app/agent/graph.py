from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.food_table import MIN_DAILY_COST
from app.agent.llm import DeepSeekLLM, MockLLM
from app.agent.tools import (
    calculate_bmi,
    calculate_bmr,
    check_allergens,
    check_budget,
    check_known_ingredients,
    check_nutrition,
)
from app.config import settings
from app.schemas import DietPlan, DietRequest


class AgentState(TypedDict):
    request: DietRequest
    plan: DietPlan | None
    violations: list[str]
    retry_count: int
    max_retries: int
    status: Literal["pending", "success", "failed"]
    bmi: float | None
    bmr: float | None
    infeasible_reason: str | None


def _make_llm():
    if settings.llm.provider == "deepseek":
        return DeepSeekLLM()
    return MockLLM()


_llm = _make_llm()


def calculate_metrics(state: AgentState) -> dict:
    req = state["request"]
    return {
        "bmi": calculate_bmi(req.height, req.weight),
        "bmr": calculate_bmr(req.age, req.gender, req.height, req.weight),
    }


def check_feasibility(state: AgentState) -> dict:
    """调模型之前先判断预算是否根本不可行。"""
    req = state["request"]
    if req.daily_budget < MIN_DAILY_COST:
        return {
            "infeasible_reason": (
                f"预算 {req.daily_budget} 元低于一日最低可行成本 "
                f"{MIN_DAILY_COST} 元，无法在保证营养的前提下生成食谱"
            ),
            "status": "failed",
        }
    return {"infeasible_reason": None}


def route_after_feasibility(state: AgentState) -> Literal["infeasible", "generate"]:
    return "infeasible" if state.get("infeasible_reason") else "generate"


def generate(state: AgentState) -> dict:
    plan = _llm.generate_plan(
        state["request"],
        feedback=state["violations"] or None,
    )
    return {"plan": plan}


def review(state: AgentState) -> dict:
    req = state["request"]
    plan = state["plan"]
    bmr = state["bmr"] or 0.0

    violations = (
        check_allergens(plan, req.allergies)
        + check_known_ingredients(plan)
        + check_budget(plan, req.daily_budget)
        + check_nutrition(plan, bmr, req.goal, req.weight)
    )
    return {
        "violations": violations,
        "status": "success" if not violations else "pending",
    }


def prepare_retry(state: AgentState) -> dict:
    return {"retry_count": state["retry_count"] + 1}


def fallback(state: AgentState) -> dict:
    return {"status": "failed"}


def route_after_review(state: AgentState) -> Literal["accept", "retry", "fail"]:
    if not state["violations"]:
        return "accept"
    if state["retry_count"] >= state["max_retries"]:
        return "fail"
    return "retry"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("calculate_metrics", calculate_metrics)
    builder.add_node("check_feasibility", check_feasibility)
    builder.add_node("generate", generate)
    builder.add_node("review", review)
    builder.add_node("prepare_retry", prepare_retry)
    builder.add_node("fallback", fallback)

    builder.add_edge(START, "calculate_metrics")
    builder.add_edge("calculate_metrics", "check_feasibility")
    builder.add_conditional_edges(
        "check_feasibility",
        route_after_feasibility,
        {"infeasible": END, "generate": "generate"},
    )
    builder.add_edge("generate", "review")
    builder.add_conditional_edges(
        "review",
        route_after_review,
        {"accept": END, "retry": "prepare_retry", "fail": "fallback"},
    )
    builder.add_edge("prepare_retry", "generate")
    builder.add_edge("fallback", END)

    return builder.compile()
