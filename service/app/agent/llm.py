import json
from app.agent.food_table import MIN_TEST_BUDGET, prompt_table
from app.agent.tools import analyze_plan, calculate_bmr, min_daily_kcal, min_daily_protein
from pydantic import ValidationError
from openai import OpenAI, OpenAIError
from app.schemas import DietPlan, DietRequest, JudgeVerdict, QualityIssue
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

    def judge_plan(
            self,
            request: DietRequest,
            plan: DietPlan,
            bmi: float,
            bmr: float,
    ) -> JudgeVerdict:
        """模拟质量审查：初次生成的 Mock 方案被否决。"""
        if plan.notes.startswith("Mock 初次"):
            return JudgeVerdict(
                approved=False,
                score=30,
                issues=[
                    QualityIssue(
                        category="meal_structure",
                        severity="blocking",
                        evidence="Mock 初次方案缺少晚餐，三餐结构不完整",
                        suggestion="补充一顿包含主食、蛋白质和蔬菜的晚餐",
                    )
                ],
                summary="Mock 初审否决",
            )
        return JudgeVerdict(
            approved=True,
            score=92,
            summary="Mock 质量审查通过",
        )



SYSTEM_PROMPT = (
    "你是一名专业营养师。根据用户的身体数据、目标、预算和饮食禁忌设计一日三餐。"
    
    "你只能使用用户提供的允许食材清单中的食材，名称必须与清单完全一致。"
    "不要输出任何成本、热量或蛋白质数值字段，这些由系统统一计算。"
    "在保证营养与禁忌的前提下尽量用足预算，通过增加食材种类和优质蛋白提升方案质量，"
    "你是厨师，搭配的菜品要合理，蔬菜不少于300g，豆制品不是蔬菜。牛奶不得低于100g，水果不能等于100g，主食的能量供比不能大于60%，油不低于20g，盐不少于3g，非主食蛋白占比≥50%"
    "不要只给最低成本的搭配。"
    "只输出符合给定 JSON 结构的数据，不要输出任何解释性文字。"
)

JUDGE_SYSTEM_PROMPT = (
    "你是一名独立的食谱质量审查员，只对确定性规则无法判断的质量问题行使否决权。"
    "系统给出的成本、热量、蛋白质、BMI 和 BMR 均来自 Python 工具，是事实数据，"
    "禁止重新计算或质疑系统给出的数值；不要重复审查过敏原或是否超过预算。"
    "你的核心职责是判断整份一日三餐是否现实、可执行，以及能否作为日常饮食长期遵循，"
    "而不只是数值是否达标。"
    "需要审查：三餐结构、菜品与食材搭配、份量、烹饪可行性、多样性、"
    "方案是否符合用户目标，以及按实际总成本能否在现实中买到、制作并长期正常食用。"
    "如果方案在现实中不可执行，例如成本明显不足以覆盖一日正常饮食、份量明显吃不饱或吃不完、"
    "食材组合无法正常烹饪、使用异常份量凑够营养指标，或者食材和菜品高度重复、结构单调、"
    "依赖极端低价或特殊采购，导致正常人无法连续多日遵循，"
    "必须判为 realism 的 blocking 问题，并设置 approved=false。"
    "即使热量、蛋白质和预算都已达标，只要方案不能长期遵循，仍然必须 blocking。"
    "禁止因为个人口味、风格偏好或缺乏证据的猜测而否决。"
    "每个 blocking 问题必须写明具体餐次、菜品或食材作为 evidence，并给出可执行的 suggestion。"
    "只有存在 blocking 问题时才能 approved=false；没有 blocking 问题时 approved 必须为 true，"
    "其他问题可使用 major 或 minor。"
    "只输出符合给定 JSON 结构的对象，不要输出解释性文字。"
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

    def judge_plan(
            self,
            request: DietRequest,
            plan: DietPlan,
            bmi: float,
            bmr: float,
    ) -> JudgeVerdict:
        prompt = self._build_judge_prompt(request, plan, bmi, bmr)
        last_error = None
        for _ in range(self.max_parse_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                raw = resp.choices[0].message.content or "{}"
                data = self._extract_json(raw)
                return JudgeVerdict.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
            except OpenAIError as e:
                raise PlanGenerationError(f"调用审查模型失败：{e}") from e
        raise PlanGenerationError(
            f"审查模型连续 {self.max_parse_retries} 次未返回合法判定：{last_error}"
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
        # 软引导的目标成本下限：尽量用足预算，但不能给出超过预算的目标
        budget_low = min(
            request.daily_budget,
            max(MIN_TEST_BUDGET, request.daily_budget * 0.6),
        )

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
            "- 方案必须现实可执行：不能用异常小份量、单一食材或不可能的成本凑够指标；"
            "质量审查会驳回现实中不可执行的方案",
            "- 三餐热量应相对均衡：午餐不少于全天的 20%，晚餐不超过 45%。",
            "- 晚餐蛋白质不要超过全天的 55%。",
            "- 午餐和晚餐不能使用同一种蔬菜，全天水果不少于 100 g。",
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

    def _build_judge_prompt(
            self,
            request: DietRequest,
            plan: DietPlan,
            bmi: float,
            bmr: float,
    ) -> str:
        analysis = analyze_plan(plan)
        schema = json.dumps(JudgeVerdict.model_json_schema(), ensure_ascii=False)
        request_data = json.dumps(
            request.model_dump(), ensure_ascii=False, indent=2
        )
        plan_data = json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)

        return "\n".join([
            "以下食谱已经通过过敏原、允许食材、预算、热量和蛋白质的硬规则校验。",
            "请只依据质量审查标准给出否决或批准结论，不要修改食谱。",
            "",
            "用户需求：",
            request_data,
            "",
            "系统确定性计算（事实数据，禁止推翻）：",
            f"- 成本：{analysis.cost:.2f} 元，预算：{request.daily_budget:.2f} 元",
            f"- 热量：{analysis.kcal:.1f} kcal",
            f"- 蛋白质：{analysis.protein:.1f} g",
            f"- BMI：{bmi:.1f}",
            f"- BMR：{bmr:.1f} kcal",
            "",
            "待审查食谱：",
            plan_data,
            "",
            "质量审查标准：",
            "- 早餐、午餐、晚餐是否完整，各餐是否有合理的主食、蛋白质和蔬果。",
            "- 同一餐中的食材和菜品是否可以实际烹饪、搭配是否合理。",
            "- 单份用量是否明显超出正常饮食范围，或小到无法提供饱腹感。",
            "- 三餐是否严重重复，缺少基本多样性。",
            "- 方案是否明显不符合减脂、维持或增肌目标。",
            "- 整体现实性：结合实际总成本、食材用量和一般市场价格，这一天饮食"
            "能否被真实购买、制作并正常吃完；明显不现实时必须给出 realism/blocking。",
            "- 长期可遵循性：方案是否因食材高度重复、菜品雷同、极端低成本、份量异常"
            "或采购困难而无法连续多日执行。即使热量、蛋白质和预算都达标，"
            "只要不能长期遵循，也必须返回 category=realism、severity=blocking、approved=false。",
            "- 重点检查三餐热量和蛋白质分配、午餐与晚餐是否重复使用同一种蔬菜、"
            "以及全天水果是否充足；这些方面明显失衡同样属于长期不可遵循。",
            "",
            "只返回符合以下 JSON Schema 的对象：",
            schema,
        ])


