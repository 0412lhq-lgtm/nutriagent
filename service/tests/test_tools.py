import pytest

from app.agent.food_table import FOODS, lookup
from app.agent.tools import (
    analyze_plan,
    calculate_bmi,
    calculate_bmr,
    check_allergens,
    check_budget,
    check_known_ingredients,
    check_nutrition,
    decorate_plan,
    min_daily_kcal,
    min_daily_protein,
)
from app.schemas import DietPlan


def make_plan(*ingredients: tuple[str, float]) -> DietPlan:
    """用 (食材名, 克数) 快速拼一个单餐食谱。"""
    return DietPlan.model_validate(
        {
            "meals": [
                {
                    "name": "早餐",
                    "dishes": [
                        {
                            "name": "测试菜",
                            "ingredients": [
                                {"name": name, "amount_g": grams}
                                for name, grams in ingredients
                            ],
                        }
                    ],
                }
            ]
        }
    )


def test_calculate_bmi():
    assert calculate_bmi(180, 75) == pytest.approx(23.1)


def test_calculate_bmr_male_and_female():
    assert calculate_bmr(30, "male", 180, 75) == 1730.0
    assert calculate_bmr(30, "female", 180, 75) == 1564.0


def test_min_daily_kcal_by_goal():
    assert min_daily_kcal(1600, "lose") == 1440
    assert min_daily_kcal(1600, "maintain") == 1600
    assert min_daily_kcal(1600, "gain") == 1760


def test_min_daily_protein_has_floor():
    assert min_daily_protein(45) == 50  # 体重太轻时不低于 50g
    assert min_daily_protein(80) == 80


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("豆腐", "北豆腐"),
        ("西红柿", "番茄"),
        ("马铃薯", "土豆"),
        ("包菜", "卷心菜"),
        ("鸡胸", "鸡胸肉"),
    ],
)
def test_lookup_supports_aliases(alias: str, canonical: str):
    assert lookup(alias) == FOODS[canonical]


def test_lookup_unknown_food_returns_none():
    assert lookup("神秘果") is None


def test_analyze_plan_sums_cost_kcal_protein():
    analysis = analyze_plan(make_plan(("燕麦", 80), ("香蕉", 150)))
    assert analysis.cost == 2.25
    assert analysis.kcal == 441.1
    assert analysis.protein == 14.1
    assert analysis.unknown == []


def test_analyze_plan_reports_unknown_ingredients():
    analysis = analyze_plan(make_plan(("燕麦", 80), ("神秘果", 100)))
    assert analysis.unknown == ["神秘果"]
    # 表外食材不计价，只统计已知部分
    assert analysis.cost == 1.2


def test_check_allergens_matches_aliases():
    plan = make_plan(("花生酱", 30))
    violations = check_allergens(plan, ["花生"])
    assert len(violations) == 1
    assert "花生酱" in violations[0]
    assert "花生" in violations[0]


def test_check_allergens_clean_plan():
    assert check_allergens(make_plan(("燕麦", 50)), ["花生", "牛奶"]) == []


def test_check_known_ingredients():
    assert check_known_ingredients(make_plan(("燕麦", 50))) == []
    violations = check_known_ingredients(make_plan(("神秘果", 50)))
    assert len(violations) == 1
    assert "神秘果" in violations[0]


def test_check_budget_uses_table_price():
    plan = make_plan(("牛排", 800))  # 9 元/100g → 72 元
    violations = check_budget(plan, 30)
    assert len(violations) == 1
    assert "72.0" in violations[0]
    assert check_budget(plan, 100) == []


def test_check_nutrition_detects_low_kcal_and_protein():
    violations = check_nutrition(
        make_plan(("白菜", 100)), bmr=1600, goal="maintain", weight_kg=70
    )
    assert len(violations) == 2
    assert "热量" in violations[0]
    assert "蛋白质" in violations[1]


def test_decorate_plan_adds_totals_and_per_ingredient_values():
    data = decorate_plan(make_plan(("燕麦", 80), ("香蕉", 150)))
    assert data["total_cost"] == 2.25
    assert data["total_kcal"] == 441.1
    assert data["total_protein"] == 14.1

    first = data["meals"][0]["dishes"][0]["ingredients"][0]
    assert first["cost"] == 1.2
    assert first["kcal"] == 301.6
    assert first["protein"] == 12.0


def test_decorate_plan_marks_unknown_cost_none():
    data = decorate_plan(make_plan(("神秘果", 100)))
    ingredient = data["meals"][0]["dishes"][0]["ingredients"][0]
    assert ingredient["cost"] is None
    assert data["total_cost"] == 0.0
