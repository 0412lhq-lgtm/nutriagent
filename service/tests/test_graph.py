from app.agent import graph as graph_module
from app.agent.graph import build_graph
from app.agent.llm import MockLLM, PlanGenerationError
from app.schemas import DietPlan, DietRequest, JudgeVerdict, QualityIssue


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
        "quality_verdict": None,
        "quality_feedback": [],
        "retry_count": 0,
        "max_retries": max_retries,
        "status": "pending",
        "bmi": None,
        "bmr": None,
        "infeasible_reason": None,
    }


PASSING_PLAN = {
    "meals": [
        {
            "name": "早餐",
            "dishes": [
                {
                    "name": "燕麦牛奶香蕉粥",
                    "ingredients": [
                        {"name": "燕麦", "amount_g": 80},
                        {"name": "牛奶", "amount_g": 200},
                        {"name": "香蕉", "amount_g": 150},
                    ],
                }
            ],
        },
        {
            "name": "午餐",
            "dishes": [
                {
                    "name": "鸡胸肉饭",
                    "ingredients": [
                        {"name": "米饭", "amount_g": 300},
                        {"name": "鸡胸肉", "amount_g": 200},
                        {"name": "西兰花", "amount_g": 200},
                        {"name": "食用油", "amount_g": 10},
                    ],
                }
            ],
        },
        {
            "name": "晚餐",
            "dishes": [
                {
                    "name": "豆腐菠菜饭",
                    "ingredients": [
                        {"name": "米饭", "amount_g": 250},
                        {"name": "北豆腐", "amount_g": 250},
                        {"name": "菠菜", "amount_g": 200},
                        {"name": "食用油", "amount_g": 10},
                    ],
                }
            ],
        },
    ],
    "notes": "用于质量审查测试的合规方案",
}


def veto_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        approved=False,
        score=50,
        issues=[
            QualityIssue(
                category="meal_structure",
                severity="blocking",
                evidence="晚餐只有一道菜，结构过于单一",
                suggestion="为晚餐增加一份优质蛋白来源",
            )
        ],
        summary="需要修改",
    )


class QualityGateLLM:
    """硬规则始终通过，只测试质量审查节点的否决和重试。"""

    def __init__(self, verdicts: list[JudgeVerdict]):
        self.verdicts = verdicts
        self.feedbacks: list[list[str] | None] = []
        self.judge_calls = 0

    def generate_plan(self, request, feedback=None):
        self.feedbacks.append(feedback)
        return DietPlan.model_validate(PASSING_PLAN)

    def judge_plan(self, request, plan, bmi, bmr):
        verdict = self.verdicts[min(self.judge_calls, len(self.verdicts) - 1)]
        self.judge_calls += 1
        return verdict


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

    def judge_plan(self, request, plan, bmi, bmr):
        raise AssertionError("硬规则未通过时不应调用 LLM Judge")


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
    assert "10.0" in result["infeasible_reason"]
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


def test_quality_veto_triggers_rewrite_with_feedback(monkeypatch):
    llm = QualityGateLLM([
        veto_verdict(),
        JudgeVerdict(approved=True, score=95, summary="修改后通过"),
    ])
    monkeypatch.setattr(graph_module, "_llm", llm)

    result = build_graph().invoke(initial_state(make_request(), max_retries=2))

    assert result["status"] == "success"
    assert result["retry_count"] == 1
    assert llm.judge_calls == 2
    assert llm.feedbacks[0] is None
    assert llm.feedbacks[1] and "质量审查" in llm.feedbacks[1][0]
    assert result["quality_verdict"].approved is True


def test_quality_veto_respects_max_retries(monkeypatch):
    llm = QualityGateLLM([veto_verdict()])
    monkeypatch.setattr(graph_module, "_llm", llm)

    result = build_graph().invoke(initial_state(make_request(), max_retries=1))

    assert result["status"] == "failed"
    assert result["retry_count"] == 1
    assert llm.judge_calls == 2
    assert result["violations"] == []
    assert result["quality_feedback"]


def test_judge_error_fails_closed_without_returning_plan(monkeypatch):
    class BrokenJudgeLLM(QualityGateLLM):
        def judge_plan(self, request, plan, bmi, bmr):
            raise PlanGenerationError("审查模型不可用")

    monkeypatch.setattr(graph_module, "_llm", BrokenJudgeLLM([]))

    result = build_graph().invoke(initial_state(make_request()))

    assert result["status"] == "failed"
    assert result["retry_count"] == 0
    assert "审查" in result["quality_feedback"][0]