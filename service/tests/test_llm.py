"""DeepSeekLLM 的解析重试测试：不请求真实接口，用假 client 注入非法 JSON。"""

import json
from types import SimpleNamespace

import pytest

import app.agent.llm as llm_module
from app.agent.llm import DeepSeekLLM, JUDGE_SYSTEM_PROMPT, PlanGenerationError
from app.schemas import DietPlan, DietRequest, JudgeVerdict

VALID_PLAN = {
    "meals": [
        {
            "name": "早餐",
            "dishes": [
                {"name": "燕麦粥", "ingredients": [{"name": "燕麦", "amount_g": 50}]}
            ],
        }
    ],
    "notes": "",
}

VALID_VERDICT = {
    "approved": False,
    "score": 55,
    "issues": [
        {
            "category": "meal_structure",
            "severity": "blocking",
            "evidence": "食谱只有早餐，缺少午餐和晚餐",
            "suggestion": "补充午餐和晚餐",
        }
    ],
    "summary": "三餐不完整",
}


def make_request() -> DietRequest:
    return DietRequest(
        age=25,
        gender="male",
        height=175,
        weight=70,
        allergies=[],
        dislikes=[],
        daily_budget=30,
        goal="maintain",
    )


class FakeCompletions:
    """按顺序返回预设的 content，模拟模型每次的输出。"""

    def __init__(self, contents: list[str]):
        self.contents = contents
        self.calls = 0

    def create(self, **kwargs):
        content = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeClient:
    def __init__(self, contents: list[str]):
        self.chat = SimpleNamespace(completions=FakeCompletions(contents))


def make_llm(monkeypatch, contents: list[str]):
    """构造 DeepSeekLLM，但把 OpenAI 客户端换成假实现。"""
    fake_client = FakeClient(contents)
    monkeypatch.setattr(llm_module, "OpenAI", lambda **kwargs: fake_client)
    return DeepSeekLLM(), fake_client.chat.completions


def test_invalid_json_then_valid_succeeds(monkeypatch):
    llm, completions = make_llm(
        monkeypatch,
        ["这不是 JSON，只是一段解释文字", json.dumps(VALID_PLAN, ensure_ascii=False)],
    )

    plan = llm.generate_plan(make_request(), feedback=None)

    assert plan.meals[0].name == "早餐"
    assert completions.calls == 2  # 第一次非法，第二次成功


def test_invalid_json_exhausts_retries(monkeypatch):
    llm, completions = make_llm(monkeypatch, ["not json", "still not json"])

    with pytest.raises(PlanGenerationError, match="模型连续 2 次未返回合法食谱"):
        llm.generate_plan(make_request(), feedback=None)

    assert completions.calls == 2  # max_parse_retries = 2，不会无限重试


def test_markdown_fenced_json_is_accepted(monkeypatch):
    fenced = "```json\n" + json.dumps(VALID_PLAN, ensure_ascii=False) + "\n```"
    llm, completions = make_llm(monkeypatch, [fenced])

    plan = llm.generate_plan(make_request(), feedback=None)

    assert plan.notes == ""
    assert completions.calls == 1  # 代码块包装能被正确剥离


def test_judge_parses_structured_veto(monkeypatch):
    llm, completions = make_llm(
        monkeypatch, [json.dumps(VALID_VERDICT, ensure_ascii=False)]
    )
    plan = DietPlan.model_validate(VALID_PLAN)

    verdict = llm.judge_plan(make_request(), plan, bmi=22.9, bmr=1700)

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.approved is False
    assert verdict.issues[0].severity == "blocking"
    assert completions.calls == 1


def test_judge_retries_invalid_json_then_succeeds(monkeypatch):
    approved = {
        "approved": True,
        "score": 90,
        "issues": [],
        "summary": "搭配合理",
    }
    llm, completions = make_llm(
        monkeypatch,
        ["无法解析的输出", json.dumps(approved, ensure_ascii=False)],
    )
    plan = DietPlan.model_validate(VALID_PLAN)

    verdict = llm.judge_plan(make_request(), plan, bmi=22.9, bmr=1700)

    assert verdict.approved is True
    assert completions.calls == 2


def test_judge_rejects_inconsistent_verdict(monkeypatch):
    inconsistent = {
        "approved": True,
        "score": 80,
        "issues": [
            {
                "category": "portion",
                "severity": "blocking",
                "evidence": "米饭 2000g，份量明显不合理",
                "suggestion": "把米饭降到 200g 左右",
            }
        ],
        "summary": "矛盾判定",
    }
    llm, completions = make_llm(
        monkeypatch,
        [json.dumps(inconsistent, ensure_ascii=False)] * 2,
    )
    plan = DietPlan.model_validate(VALID_PLAN)

    with pytest.raises(PlanGenerationError, match="未返回合法判定"):
        llm.judge_plan(make_request(), plan, bmi=22.9, bmr=1700)

    assert completions.calls == 2


def test_judge_prompt_requires_long_term_adherence(monkeypatch):
    llm, _ = make_llm(monkeypatch, ["{}"])
    plan = DietPlan.model_validate(VALID_PLAN)

    prompt = llm._build_judge_prompt(make_request(), plan, bmi=22.9, bmr=1700)

    assert "长期可遵循性" in prompt
    assert "category=realism" in prompt
    assert "severity=blocking" in prompt
    assert "approved=false" in prompt
    assert "不能长期遵循" in JUDGE_SYSTEM_PROMPT
