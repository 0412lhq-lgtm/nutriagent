from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.food_table import MIN_TEST_BUDGET
from app.agent.llm import DeepSeekLLM, MockLLM, PlanGenerationError
from app.agent.realism import audit_plan_realism
from app.agent.tools import (
    calculate_bmi,
    calculate_bmr,
    check_allergens,
    check_budget,
    check_known_ingredients,
    check_nutrition,
)
from app.config import settings
from app.schemas import DietPlan, DietRequest, JudgeVerdict


class AgentState(TypedDict):
    request: DietRequest
    plan: DietPlan | None
    violations: list[str]
    quality_verdict: JudgeVerdict | None
    quality_feedback: list[str]
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
    if req.daily_budget < MIN_TEST_BUDGET:
        return {
            "infeasible_reason": (
                f"预算 {req.daily_budget} 元低于允许测试的最低预算 "
                f"{MIN_TEST_BUDGET} 元，无法进入生成流程"
            ),
            "status": "failed",
        }
    return {"infeasible_reason": None}


def route_after_feasibility(state: AgentState) -> Literal["infeasible", "generate"]:
    return "infeasible" if state.get("infeasible_reason") else "generate"


def generate(state: AgentState) -> dict:
    feedback = state["violations"] + state.get("quality_feedback", [])
    plan = _llm.generate_plan(
        state["request"],
        feedback=feedback or None,
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
        "status": "pending",
    }


def _apply_realism_policy(
    verdict: JudgeVerdict,
    plan: DietPlan,
) -> JudgeVerdict:
    """用确定性规则兜底，保证无法长期遵循的方案一定被否决。"""
    policy_issues = audit_plan_realism(plan)
    if not policy_issues:
        return verdict

    existing = {(issue.category, issue.evidence) for issue in verdict.issues}
    new_issues = [
        issue
        for issue in policy_issues
        if (issue.category, issue.evidence) not in existing
    ]
    if not new_issues:
        return verdict

    return JudgeVerdict(
        approved=False,
        score=min(verdict.score, 60),
        issues=[*verdict.issues, *new_issues],
        summary="长期可遵循性审查未通过",
    )


def quality_review(state: AgentState) -> dict:
    """独立质量审查节点：只输出判定和意见，不修改食谱。"""
    plan = state["plan"]
    if plan is None:
        return {
            "quality_verdict": None,
            "quality_feedback": ["质量审查失败：没有可供审查的食谱"],
            "status": "failed",
        }

    try:
        verdict = _llm.judge_plan(
            state["request"],
            plan,
            bmi=state["bmi"] or 0.0,
            bmr=state["bmr"] or 0.0,
        )
    except PlanGenerationError as e:
        return {
            "quality_verdict": None,
            "quality_feedback": [f"质量审查失败：{e}"],
            "status": "failed",
        }

    verdict = _apply_realism_policy(verdict, plan)
    feedback = [
        (
            f"[质量审查/{issue.severity}] {issue.evidence}"
            f"；建议：{issue.suggestion}"
        )
        for issue in verdict.issues
    ]
    return {
        "quality_verdict": verdict,
        "quality_feedback": feedback,
        "status": "success" if verdict.approved else "pending",
    }


def prepare_retry(state: AgentState) -> dict:
    return {"retry_count": state["retry_count"] + 1}


def fallback(state: AgentState) -> dict:
    return {"status": "failed"}


def route_after_review(state: AgentState) -> Literal["quality", "retry", "fail"]:
    if not state["violations"]:
        return "quality"
    if state["retry_count"] >= state["max_retries"]:
        return "fail"
    return "retry"


def route_after_quality(state: AgentState) -> Literal["accept", "retry", "fail"]:
    verdict = state.get("quality_verdict")
    if verdict is not None and verdict.approved:
        return "accept"
    if state["status"] == "failed":
        return "fail"
    if state["retry_count"] >= state["max_retries"]:
        return "fail"
    return "retry"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("calculate_metrics", calculate_metrics)
    builder.add_node("check_feasibility", check_feasibility)
    builder.add_node("generate", generate)
    builder.add_node("review", review)
    builder.add_node("quality_review", quality_review)
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
        {"quality": "quality_review", "retry": "prepare_retry", "fail": "fallback"},
    )
    builder.add_conditional_edges(
        "quality_review",
        route_after_quality,
        {"accept": END, "retry": "prepare_retry", "fail": "fallback"},
    )
    builder.add_edge("prepare_retry", "generate")
    builder.add_edge("fallback", END)

    return builder.compile()
