import json
from app.agent.food_table import MIN_DAILY_COST, prompt_table
from app.agent.tools import calculate_bmr, min_daily_kcal, min_daily_protein
from pydantic import ValidationError
from openai import OpenAI, OpenAIError
from app.schemas import DietPlan, DietRequest
from app.config import settings

class MockLLM:
    """模拟大模型：第一次故意生成违规食谱，收到反馈后生成合规食谱。"""

    def generate_plan(
            self,
            request: DietRequest,
            feedback: list[str] | None = None,
    ) -> DietPlan:
        if feedback:
            data = self._compliant_plan(request)
        else:
            data = self._violating_plan(request)
        return DietPlan.model_validate(data)

    def _violating_plan(self, request: DietRequest) -> dict:
        """故意含过敏原，且在真实价格下远超预算。"""
        allergen = request.allergies[0] if request.allergies else "花生"
        return {
            "meals": [
                {
                    "name": "早餐",
                    "dishes": [
                        {
                            "name": f"{allergen}吐司",
                            "ingredients": [
                                {"name": f"{allergen}酱", "amount_g": 30},
                                {"name": "吐司", "amount_g": 100},
                            ],
                        }
                    ],
                },
                {
                    "name": "午餐",
                    "dishes": [
                        {
                            "name": "豪华牛排",
                            "ingredients": [{"name": "牛排", "amount_g": 800}],
                        }
                    ],
                },
            ],
            "notes": "Mock 初次生成：故意违规",
        }

    def _compliant_plan(self, request: DietRequest) -> dict:
        """真实成本约 12.7 元、约 1900 kcal、蛋白约 111 g，可过三条硬规则。"""
        return {
            "meals": [
                {
                    "name": "早餐",
                    "dishes": [
                        {
                            "name": "燕麦香蕉粥",
                            "ingredients": [
                                {"name": "燕麦", "amount_g": 80},
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
            "notes": "Mock 根据反馈重写：已去除过敏原并压低成本",
        }



SYSTEM_PROMPT = (
    "你是一名专业营养师。根据用户的身体数据、目标、预算和饮食禁忌设计一日三餐。"
    
    "你只能使用用户提供的允许食材清单中的食材，名称必须与清单完全一致。"
    "不要输出任何成本、热量或蛋白质数值字段，这些由系统统一计算。"
    "在保证营养与禁忌的前提下尽量用足预算，通过增加食材种类和优质蛋白提升方案质量，"
    "你是厨师，搭配的菜品要合理，蔬菜不少于300g，豆制品不是蔬菜。牛奶不得低于100g，水果不能等于100g，主食的能量供比不能大于60%，油不低于20g，盐不少于3g，非主食蛋白占比≥50%"
    "不要只给最低成本的搭配。"
    "只输出符合给定 JSON 结构的数据，不要输出任何解释性文字。"
)
class PlanGenerationError(Exception):
    """真实模型多次尝试后仍无法产出合法食谱。"""
class DeepSeekLLM():
    def __init__(self):
        self.max_parse_retries=2
        self.client:OpenAI=OpenAI(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
            timeout=settings.llm.timeout,   # 单次请求最长等待，可在 .env 用 LLM_TIMEOUT 调
            max_retries=1,                  # 连接类错误 SDK 自动重试 1 次
        )
        self.model=settings.llm.model

    def generate_plan(self,request:DietRequest,feedback:list[str]|None)->DietPlan:
        promot=self._build_prompt(request,feedback)
        last_error=None
        for attempt in range(self.max_parse_retries):
            try:
                resp=self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role":"system","content":SYSTEM_PROMPT},
                             {"role":"user","content":promot}],
                    response_format={"type":"json_object"},
                    temperature=0.7 if attempt==0 else 0.3
                )
                raw=resp.choices[0].message.content or "{}"
                data=self._extract_json(raw)
                return DietPlan.model_validate(data)
            except(json.JSONDecodeError,ValidationError) as e:
                last_error=e
            except OpenAIError as e:
                # 超时/断网/接口报错：不属于"格式不对"，直接转 502，不再解析重试
                raise PlanGenerationError(f"调用模型失败：{e}") from e
        raise PlanGenerationError(
            f"模型连续 {self.max_parse_retries} 次未返回合法食谱：{last_error}"
        )
    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        return json.loads(text)

    def _build_prompt(self, request: DietRequest, feedback: list[str] | None) -> str:
        schema = json.dumps(DietPlan.model_json_schema(), ensure_ascii=False)
        bmr = calculate_bmr(request.age, request.gender, request.height, request.weight)
        floor_kcal = min_daily_kcal(bmr, request.goal)
        floor_protein = min_daily_protein(request.weight)
        goal_text = {"lose": "减脂", "maintain": "维持", "gain": "增肌"}[request.goal]
        # 软引导的目标成本下限：预算的 60%，但不低于系统最低可行成本
        budget_low = max(MIN_DAILY_COST, request.daily_budget * 0.6)

        lines = [
            "请为下述用户设计一日三餐（必须包含早餐、午餐、晚餐）：",
            f"- 年龄：{request.age}，性别：{request.gender}",
            f"- 身高：{request.height} cm，体重：{request.weight} kg",
            f"- 目标：{goal_text}",
            f"- 每日预算：{request.daily_budget} 元（所有食材成本由系统计算，不得超过）",
            f"- 预算利用：请在营养均衡的前提下把总成本做到 "
            f"{budget_low:.1f}~{request.daily_budget:.1f} 元（预算的 60%~100%），"
            f"通过增加食材种类、优质蛋白（肉蛋奶）和水果把预算用足；"
            f"若预算明显偏高，以营养均衡为准，不必刻意花完，也不要让热量明显超标",
            f"- 每日最低热量：{floor_kcal:.0f} kcal（必须达到）",
            f"- 每日最低蛋白质：{floor_protein:.0f} g（必须达到）",
            f"- 过敏原（绝对不能出现）：{request.allergies or '无'}",
            f"- 忌口：{request.dislikes or '无'}",
            "",
            "只能使用下列食材（名称必须完全一致，清单外食材视为违规）：",
            prompt_table(),
            "",
            "严格返回如下 JSON 结构，不要包含 markdown 代码块或额外文字：",
            schema,
        ]
        if feedback:
            lines.append("")
            lines.append("你上一版生成的食谱存在以下问题，请针对性修正后重新输出完整 JSON：")
            lines.extend(f"- {v}" for v in feedback)
        return "\n".join(lines)


