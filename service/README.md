# service · NutriAgent 后端

FastAPI + LangGraph 实现的膳食规划服务。整体介绍、前端与 Docker 部署见[项目根目录 README](../README.md)。

## 目录

```
app/
├─ agent/
│  ├─ graph.py       LangGraph 状态机：计算指标 → 预算预检 → 生成 → 审查 → 重试 / 降级
│  ├─ llm.py         MockLLM（离线演示）与 DeepSeekLLM（OpenAI 兼容接口）
│  ├─ tools.py       BMI/BMR、四类审查规则、成本/营养汇总
│  └─ food_table.py  食材价格与营养成分表（审查白名单的依据）
├─ config.py         pydantic-settings，读取 service/.env 与环境变量
├─ database.py       SQLAlchemy 引擎 / SessionLocal
├─ models.py         diet_records 表
├─ schemas.py        DietRequest / DietResponse / DietPlan 等
└─ main.py           FastAPI 应用、CORS、路由、异常映射
```

## 本地运行

```bash
cd service
cp .env.example .env        # 修改 MYSQL_*；默认 LLM_PROVIDER=mock，无需 API Key
uv sync
uv run uvicorn app.main:api --reload --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>

## 测试

```bash
uv run pytest -q            # 22 passed
```

`tests/conftest.py` 在导入应用前把 `LLM_PROVIDER` 固定为 `mock`，并填入占位的 `MYSQL_*`，因此测试不会访问真实模型，也不依赖本地 `.env`。

## 审查规则

生成结果必须依次通过四类检查，任一不通过都会把原因回传给模型重试：

1. 过敏原：食材名 / 菜名不得包含用户过敏原；
2. 食材白名单：只能使用 `food_table.py` 中登记过的食材；
3. 预算：按食材表单价计算的总成本不得超过 `daily_budget`；
4. 营养：热量与蛋白质不得低于按 BMR、体重和目标推导的下限。

预算低于一日最低可行成本（`MIN_DAILY_COST = 6.0` 元）时，直接返回 422，不调用模型。

## 错误约定

| 状态码 | 场景 |
|---|---|
| 422 | 请求参数不合法；或预算低于最低可行成本（`detail` 为原因） |
| 502 | 模型调用失败，或连续多次未返回合法 JSON |

## 注意

- `.env`、`.venv`、`__pycache__` 等已被根目录 `.gitignore` 忽略，不要提交密钥。
- Docker 构建使用 `requirements.txt`（锁版本），本地开发使用 `pyproject.toml` + `uv.lock`。
