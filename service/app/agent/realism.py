"""长期可遵循性审查：拦截指标达标但现实中难以长期执行的方案。"""

from dataclasses import dataclass, field

from app.agent.food_table import ALIASES, lookup
from app.schemas import DietPlan, QualityIssue

MAIN_MEALS = ("早餐", "午餐", "晚餐")
MIN_VEGETABLE_GRAMS = 300
MIN_FRUIT_GRAMS = 100
MAX_DINNER_KCAL_SHARE = 0.45
MIN_LUNCH_KCAL_SHARE = 0.20
MAX_DINNER_PROTEIN_SHARE = 0.55

VEGETABLE_GROUPS = {
    "白菜": "叶菜类",
    "卷心菜": "叶菜类",
    "菠菜": "叶菜类",
    "芹菜": "叶菜类",
    "西兰花": "花菜类",
    "菜花": "花菜类",
    "胡萝卜": "根茎类",
    "土豆": "根茎类",
    "红薯": "根茎类",
    "番茄": "茄果类",
    "青椒": "茄果类",
    "黄瓜": "瓜类",
    "蘑菇": "菌菇类",
    "豆角": "豆类蔬菜",
    "玉米": "杂粮蔬菜",
}

FRUIT_NAMES = {"香蕉", "苹果", "橙子", "梨"}


@dataclass
class MealStats:
    kcal: float = 0.0
    protein: float = 0.0
    vegetables: dict[str, float] = field(default_factory=dict)


def _canonical_name(name: str) -> str:
    return ALIASES.get(name.strip(), name.strip())


def _add_meal_stats(stats: dict[str, MealStats], plan: DietPlan) -> tuple[float, float]:
    fruit_grams = 0.0
    for meal in plan.meals:
        meal_stats = stats.setdefault(meal.name, MealStats())
        for dish in meal.dishes:
            for ingredient in dish.ingredients:
                name = _canonical_name(ingredient.name)
                food = lookup(name)
                if food is None:
                    continue

                ratio = ingredient.amount_g / 100
                meal_stats.kcal += food.kcal * ratio
                meal_stats.protein += food.protein * ratio

                group = VEGETABLE_GROUPS.get(name)
                if group:
                    meal_stats.vegetables[group] = (
                        meal_stats.vegetables.get(group, 0.0)
                        + ingredient.amount_g
                    )
                if name in FRUIT_NAMES:
                    fruit_grams += ingredient.amount_g
    return fruit_grams, sum(item.kcal for item in stats.values())


def _blocking(evidence: str, suggestion: str) -> QualityIssue:
    return QualityIssue(
        category="realism",
        severity="blocking",
        evidence=evidence,
        suggestion=suggestion,
    )


def audit_plan_realism(plan: DietPlan) -> list[QualityIssue]:
    """返回阻断性现实问题；空列表表示通过长期可遵循性检查。"""
    issues: list[QualityIssue] = []
    stats: dict[str, MealStats] = {}
    fruit_grams, total_kcal = _add_meal_stats(stats, plan)
    total_protein = sum(item.protein for item in stats.values())

    present_meals = {meal.name for meal in plan.meals}
    missing_meals = [name for name in MAIN_MEALS if name not in present_meals]
    if missing_meals:
        issues.append(_blocking(
            f"缺少{'、'.join(missing_meals)}，无法构成完整的一日三餐",
            "补齐早餐、午餐和晚餐",
        ))

    if total_kcal > 0:
        lunch_share = stats.get("午餐", MealStats()).kcal / total_kcal
        dinner_share = stats.get("晚餐", MealStats()).kcal / total_kcal
        if lunch_share < MIN_LUNCH_KCAL_SHARE or dinner_share > MAX_DINNER_KCAL_SHARE:
            issues.append(_blocking(
                f"午餐仅占全天热量 {lunch_share:.0%}，晚餐占 {dinner_share:.0%}，"
                "三餐能量分配失衡",
                "把一部分主食和蛋白质移到午餐，使午餐和晚餐的能量更均衡",
            ))

    if total_protein > 0:
        dinner_protein_share = stats.get("晚餐", MealStats()).protein / total_protein
        if dinner_protein_share > MAX_DINNER_PROTEIN_SHARE:
            issues.append(_blocking(
                f"晚餐集中了全天 {dinner_protein_share:.0%} 的蛋白质，三餐蛋白质分布不均",
                "将部分蛋白质来源分配到早餐和午餐",
            ))

    total_vegetables = sum(
        sum(meal.vegetables.values()) for meal in stats.values()
    )
    if total_vegetables < MIN_VEGETABLE_GRAMS:
        issues.append(_blocking(
            f"全天蔬菜仅 {total_vegetables:.0f} g，低于长期饮食所需的"
            f" {MIN_VEGETABLE_GRAMS} g",
            "增加不同种类的蔬菜",
        ))

    lunch_groups = set(stats.get("午餐", MealStats()).vegetables)
    dinner_groups = set(stats.get("晚餐", MealStats()).vegetables)
    repeated_groups = lunch_groups & dinner_groups
    if repeated_groups:
        groups = "、".join(sorted(repeated_groups))
        issues.append(_blocking(
            f"午餐和晚餐重复使用{groups}蔬菜，菜品结构高度相似",
            "午餐和晚餐使用不同种类的蔬菜",
        ))

    if fruit_grams < MIN_FRUIT_GRAMS:
        issues.append(_blocking(
            f"全天水果仅 {fruit_grams:.0f} g，低于长期饮食所需的"
            f" {MIN_FRUIT_GRAMS} g",
            "增加一份新鲜水果，使全天水果达到至少 100 g",
        ))

    return issues
