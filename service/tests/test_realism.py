from app.agent.realism import audit_plan_realism
from app.schemas import DietPlan


def make_plan(meals: list[dict]) -> DietPlan:
    return DietPlan.model_validate({"meals": meals, "notes": ""})


UNBALANCED_PLAN = make_plan(
    [
        {
            "name": "早餐",
            "dishes": [
                {
                    "name": "小米牛奶粥",
                    "ingredients": [
                        {"name": "小米", "amount_g": 30},
                        {"name": "牛奶", "amount_g": 100},
                    ],
                },
                {
                    "name": "水煮蛋",
                    "ingredients": [{"name": "鸡蛋", "amount_g": 50}],
                },
                {
                    "name": "凉拌胡萝卜丝",
                    "ingredients": [
                        {"name": "胡萝卜", "amount_g": 30},
                        {"name": "食用油", "amount_g": 5},
                    ],
                },
                {
                    "name": "香蕉",
                    "ingredients": [{"name": "香蕉", "amount_g": 40}],
                },
            ],
        },
        {
            "name": "午餐",
            "dishes": [
                {
                    "name": "白菜豆腐面",
                    "ingredients": [
                        {"name": "面条", "amount_g": 60},
                        {"name": "北豆腐", "amount_g": 50},
                        {"name": "白菜", "amount_g": 170},
                        {"name": "食用油", "amount_g": 8},
                    ],
                }
            ],
        },
        {
            "name": "晚餐",
            "dishes": [
                {
                    "name": "米饭",
                    "ingredients": [{"name": "大米", "amount_g": 150}],
                },
                {
                    "name": "黄豆炖卷心菜",
                    "ingredients": [
                        {"name": "黄豆", "amount_g": 100},
                        {"name": "卷心菜", "amount_g": 100},
                        {"name": "食用油", "amount_g": 10.5},
                    ],
                },
            ],
        },
    ]
)

BALANCED_PLAN = make_plan(
    [
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
    ]
)


def test_unbalanced_low_variety_plan_has_blocking_issues():
    issues = audit_plan_realism(UNBALANCED_PLAN)
    evidence = "\n".join(issue.evidence for issue in issues)

    assert issues
    assert all(issue.category == "realism" for issue in issues)
    assert all(issue.severity == "blocking" for issue in issues)
    assert "三餐能量分配失衡" in evidence
    assert "蛋白质分布不均" in evidence
    assert "重复使用叶菜类蔬菜" in evidence
    assert "水果仅 40 g" in evidence


def test_balanced_plan_passes_realism_audit():
    assert audit_plan_realism(BALANCED_PLAN) == []
