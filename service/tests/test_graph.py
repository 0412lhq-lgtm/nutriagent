from app.agent import graph as graph_module
from app.agent.graph import build_graph
from app.agent.llm import MockLLM
from app.schemas import DietPlan, DietRequest


def make_request(**overrides) -> DietRequest:
    data = {
        "age": 25,
        "gender": "male",
        "height": 175,
        "weight": 70,
        "allergies": ["花生"],
        "dislikes": [],
        "daily_budget": 30,
        "goal": "maintain",
    }
    data.update(overrides)
    return DietRequest(**data)


def initial_state(request: DietRequest, max_retries: int = 2) -> dict:
    return {
        "request": request,
        "plan": None,
        "violations": [],
        "retry_count": 0,
        "max_retries": max_retries,
        "status": "pending",
        "bmi": None,
        "bmr": None,
        "infeasible_reason": None,
    }


class AlwaysViolatingLLM:
    """永远返回同一份违规食谱，用来验证重试上限与降级。"""

    def __init__(self):
        self.feedbacks: list[list[str] | None] = []

    def generate_plan(
        self, request: DietRequest, feedback: list[str] | None = None
    ) -> DietPlan:
        self.feedbacks.append(feedback)
        return DietPlan.model_validate(
            {
                "meals": [
                    {
                        "name": "早餐",
                        "dishes": [
                            {
                                "name": "牛排",
                                "ingredients": [{"name": "牛排", "amount_g": 800}],
                            }
                        ],
                    }
                ]
            }
        )


def test_mock_retry_loop_recovers_after_feedback(monkeypatch):
    monkeypatch.setattr(graph_module, "_llm", MockLLM())

    result = build_graph().invoke(initial_state(make_request()))

    assert result["status"] == "success"
    assert result["retry_count"] == 1  # 第一版违规，第二版通过
    assert result["violations"] == []
    assert result["plan"] is not None


def test_infeasible_budget_skips_llm(monkeypatch):
    class NeverCalledLLM:
        def generate_plan(self, request, feedback=None):
            raise AssertionError("预算不可行时不应调用 LLM")

    monkeypatch.setattr(graph_module, "_llm", NeverCalledLLM())

    result = build_graph().invoke(
        initial_state(make_request(daily_budget=5))
    )

    assert result["status"] == "failed"
    assert "6.0" in result["infeasible_reason"]
    assert result["plan"] is None
    assert result["retry_count"] == 0


def test_fallback_stops_after_max_retries(monkeypatch):
    llm = AlwaysViolatingLLM()
    monkeypatch.setattr(graph_module, "_llm", llm)

    result = build_graph().invoke(
        initial_state(make_request(), max_retries=2)
    )

    assert result["status"] == "failed"
    assert result["retry_count"] == 2
    assert result["violations"] != []

    # 首次生成 + 2 次重试；重试时要把违规原因回传给模型
    assert len(llm.feedbacks) == 3
    assert llm.feedbacks[0] is None
    assert llm.feedbacks[1] and llm.feedbacks[2]