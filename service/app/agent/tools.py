from dataclasses import dataclass

from app.agent.food_table import lookup
from app.schemas import DietPlan


ALLERGEN_ALIASES: dict[str, tuple[str, ...]] = {
    "花生": ("花生", "花生米", "花生酱"),
    "牛奶": ("牛奶", "鲜奶", "奶酪", "黄油", "奶油"),
    "鸡蛋": ("鸡蛋", "蛋清", "蛋黄"),
    "海鲜": ("虾", "蟹", "贝", "鱿鱼", "海鲜"),
    "大豆": ("大豆", "黄豆", "豆腐", "豆浆"),
    "小麦": ("小麦", "面粉", "面条", "面包"),
    "坚果": ("核桃", "杏仁", "腰果", "开心果", "坚果"),
    "卷心菜": ("卷心菜", "包菜", "圆白菜"),
    "番茄":   ("番茄", "西红柿"),
    "土豆":   ("土豆", "马铃薯"),
    "红薯":   ("红薯", "地瓜"),
    "鸡胸肉": ("鸡胸肉", "鸡胸"),
}


@dataclass
class PlanAnalysis:
    cost: float
    kcal: float
    protein: float
    unknown: list[str]


def analyze_plan(plan: DietPlan) -> PlanAnalysis:
    """用食物表确定性计算成本、热量、蛋白质；收集表外食材。"""
    cost = kcal = protein = 0.0
    unknown: list[str] = []

    for meal in plan.meals:
        for dish in meal.dishes:
            for ing in dish.ingredients:
                food = lookup(ing.name)
                if food is None:
                    if ing.name not in unknown:
                        unknown.append(ing.name)
                    continue

                ratio = ing.amount_g / 100
                cost += food.price * ratio
                kcal += food.kcal * ratio
                protein += food.protein * ratio

    return PlanAnalysis(round(cost, 2), round(kcal, 1), round(protein, 1), unknown)


def check_allergens(plan: DietPlan, allergens: list[str]) -> list[str]:
    violations: list[str] = []
    for meal in plan.meals:
        for dish in meal.dishes:
            for ingredient in dish.ingredients:
                for allergen in allergens:
                    keys = ALLERGEN_ALIASES.get(allergen, (allergen,))
                    if any(k in ingredient.name for k in keys):
                        violations.append(
                            f"{meal.name}-{dish.name}中的{ingredient.name}含有过敏原{allergen}"
                        )
    return violations


def check_known_ingredients(plan: DietPlan) -> list[str]:
    unknown = analyze_plan(plan).unknown
    if unknown:
        return [f"以下食材不在允许清单内，无法计价：{'、'.join(unknown)}"]
    return []


def check_budget(plan: DietPlan, daily_budget: float) -> list[str]:
    cost = analyze_plan(plan).cost
    if cost > daily_budget:
        return [
            f"总成本 {cost} 元，超过预算 {daily_budget} 元，"
            f"需减少 {round(cost - daily_budget, 2)} 元"
        ]
    return []


def min_daily_kcal(bmr: float, goal: str) -> float:
    factor = {"lose": 0.9, "maintain": 1.0, "gain": 1.1}[goal]
    return round(bmr * factor)


def min_daily_protein(weight_kg: float) -> float:
    return round(max(50.0, weight_kg * 1.0))


def check_nutrition(plan: DietPlan, bmr: float, goal: str, weight_kg: float) -> list[str]:
    analysis = analyze_plan(plan)
    violations: list[str] = []

    floor_kcal = min_daily_kcal(bmr, goal)
    floor_protein = min_daily_protein(weight_kg)

    if analysis.kcal < floor_kcal:
        violations.append(
            f"总热量约 {analysis.kcal} kcal，低于最低要求 {floor_kcal:.0f} kcal"
        )
    if analysis.protein < floor_protein:
        violations.append(
            f"蛋白质约 {analysis.protein} g，低于最低要求 {floor_protein:.0f} g"
        )
    return violations


def decorate_plan(plan: DietPlan) -> dict:
    """模型输出 + Python 计算的成本/热量/蛋白，合成可入库的结构。"""
    data = plan.model_dump()
    total_cost = total_kcal = total_protein = 0.0

    for meal in data["meals"]:
        for dish in meal["dishes"]:
            for ing in dish["ingredients"]:
                food = lookup(ing["name"])
                if food is None:
                    ing["cost"] = None
                    continue

                ratio = ing["amount_g"] / 100
                ing["cost"] = round(food.price * ratio, 2)
                ing["kcal"] = round(food.kcal * ratio, 1)
                ing["protein"] = round(food.protein * ratio, 1)

                total_cost += food.price * ratio
                total_kcal += food.kcal * ratio
                total_protein += food.protein * ratio

    data["total_cost"] = round(total_cost, 2)
    data["total_kcal"] = round(total_kcal, 1)
    data["total_protein"] = round(total_protein, 1)
    return data


def calculate_bmi(height_cm: float, weight_kg: float) -> float:
    height_m = height_cm / 100
    return round(weight_kg / height_m**2, 1)


def calculate_bmr(age: int, gender: str, height_cm: float, weight_kg: float) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        return round(base + 5, 1)
    return round(base - 161, 1)
