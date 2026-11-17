# NutriAgent · 多约束智能膳食规划系统

基于 **LangGraph** 的「生成 → 审查 → 反思重试」膳食规划服务：根据用户的身体数据、减脂/增肌目标和每日预算，生成一日三餐，并在入库前用规则引擎检查过敏原、食材白名单、成本、热量与蛋白质，违规结果会回传给模型重新生成。

前端使用 Vue 3 + Element Plus + ECharts，后端使用 FastAPI + SQLAlchemy + MySQL，模型可切换为 **DeepSeek** 或内置 **Mock**（无需 API Key 即可完整演示）。

## 功能特性

- **多约束建模**：年龄、性别、身高、体重、目标（减脂/维持/增肌）、每日预算、过敏原、忌口；自动计算 BMI / BMR，并推导每日最低热量与最低蛋白质。
- **生成-审查-重试闭环**：LangGraph 状态机串联生成、审查、重试、降级；每次审查未通过都会把违规原因回传模型，最多重试 `MAX_RETRIES` 次。
- **四类硬性审查**：过敏原、食材白名单、预算上限、营养下限（热量 / 蛋白质），全部由确定性代码计算，不依赖模型自报数值。
- **预算可行性预检**：预算低于一日最低可行成本（12 元）时直接返回 422，不浪费模型调用。
- **模型可切换**：`LLM_PROVIDER=mock` 时可离线演示完整重试流程；切换为 `deepseek` 即调用真实模型。
- **结果落库与历史查询**：每次请求的参数、最终食谱、审查反馈、重试次数和状态都会写入 MySQL，前端可回看历史记录。
- **可视化**：成本构成饼图、营养对比柱状图、逐食材成本/热量/蛋白明细表（对应 `getDietPlan` 接口）。
- **一键部署**：Docker Compose 编排 MySQL + FastAPI + Nginx 托管的前端，前端通过 Nginx 反向代理访问后端。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3、Vite 6、Element Plus、ECharts、Axios |
| 后端 | Python 3.14、FastAPI、Pydantic v2、SQLAlchemy 2、LangGraph |
| 模型 | DeepSeek（OpenAI 兼容接口）/ 内置 Mock |
| 数据 | MySQL 8.0（utf8mb4） |
| 部署 | Docker Compose、Nginx |

## 工作流程

```
START
  └─ calculate_metrics     计算 BMI / BMR
       └─ check_feasibility  预算低于最低可行成本？
            ├─ 是 → fallback（status=failed，直接返回 422）
            └─ 否 → generate    LLM 生成食谱
                      └─ review  规则引擎审查
                           ├─ 无违规 → 成功入库
                           ├─ 有违规且未达上限 → prepare_retry → generate（携带反馈重试）
                           └─ 达到上限 → fallback（status=failed）
```

审查规则（`service/app/agent/tools.py`）：

1. `check_allergens`：食材 / 菜名中不得出现用户过敏原；
2. `check_known_ingredients`：只能使用内置食材表（`food_table.py`）中的食材；
3. `check_budget`：按食材表单价计算总成本，不得超过每日预算；
4. `check_nutrition`：热量、蛋白质不得低于按 BMR 和目标推导的下限。

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 准备环境变量
cp .env.example .env        # Windows: copy .env.example .env
# 编辑 .env，至少修改 MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD

# 2. 启动（首次会构建镜像并初始化数据库）
docker compose up --build
```

启动后：

- 前端：<http://localhost:8080>
- 后端接口文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

默认 `LLM_PROVIDER=mock`，无需 API Key。要使用真实模型，在 `.env` 中设置：

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxx
LLM_MODEL=deepseek-chat
```

### 方式二：本地开发

需要本机已安装 MySQL 8.0（或用任意 MySQL 实例），并导入建表脚本：

```bash
mysql -u root -p < db/init/01_schema.sql
```

后端：

```bash
cd service
cp .env.example .env          # 按本机 MySQL 修改 MYSQL_* 配置
uv sync
uv run uvicorn app.main:api --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173，/api 由 Vite 代理到 127.0.0.1:8000
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/api/diet-plans` | 生成膳食计划并入库 |
| GET | `/api/diet-plans/{id}` | 按 ID 查询历史记录 |

请求示例：

```json
{
  "age": 25,
  "gender": "male",
  "height": 175,
  "weight": 70,
  "allergies": ["花生"],
  "dislikes": ["香菜"],
  "daily_budget": 30,
  "goal": "maintain"
}
```

字段约束：`gender` 为 `male` / `female`；`goal` 为 `lose` / `maintain` / `gain`；`height` 单位 cm（>50），`weight` 单位 kg（>10），`daily_budget` 单位元（>0）。

响应示例（节选）：

```json
{
  "id": 1,
  "status": "success",
  "retry_count": 1,
  "review_feedback": null,
  "final_plan": {
    "meals": [
      {
        "name": "早餐",
        "dishes": [
          {
            "name": "燕麦香蕉粥",
            "ingredients": [
              { "name": "燕麦", "amount_g": 80, "cost": 0.96, "kcal": 301.6, "protein": 12.0 }
            ]
          }
        ]
      }
    ],
    "notes": "Mock 根据反馈重写：已去除过敏原并压低成本",
    "total_cost": 12.71,
    "total_kcal": 1897.9,
    "total_protein": 111.1
  },
  "created_at": "2026-11-17T12:00:00"
}
```

> 上面只展示了一餐；`final_plan` 中每个食材的成本 / 热量 / 蛋白质以及整份计划的总计，都由后端用食材表统一计算并附加，模型只负责选食材和克数。

错误码：

- `422`：预算低于最低可行成本（`detail` 为具体原因），或请求参数校验失败；
- `502`：模型调用失败 / 连续多次返回非法结构。

## 配置项

| 变量 | 说明 | 默认值 |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码（仅 Compose 使用） | 无，必填 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | 应用数据库账号 | 无，必填 |
| `MYSQL_DB` | 数据库名 | `nutri_agent` |
| `MYSQL_HOST` / `MYSQL_PORT` | 数据库地址（本地开发用） | `127.0.0.1` / `3306` |
| `MAX_RETRIES` | 审查失败后的最大重试次数 | `2` |
| `LLM_PROVIDER` | `mock` 或 `deepseek` | `mock` |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `DEEPSEEK_API_KEY` | 真实模型的 API Key | 空 |
| `LLM_TIMEOUT` | 单次模型请求超时（秒） | `150` |

> **不要提交 `.env`。** 仓库只保留 `.env.example`，`.gitignore` 已忽略 `.env`、`.venv`、`node_modules`、日志等文件。

## 项目结构

```
healthy manager/
├─ db/init/01_schema.sql        # MySQL 初始化脚本（容器首次启动自动执行）
├─ docker-compose.yml           # MySQL + 后端 + 前端
├─ .env.example                 # Compose 环境变量模板
├─ service/                     # 后端
│  ├─ app/
│  │  ├─ agent/
│  │  │  ├─ graph.py            # LangGraph 状态机
│  │  │  ├─ llm.py              # DeepSeek / Mock 两种实现
│  │  │  ├─ tools.py            # BMI/BMR 与四类审查规则
│  │  │  └─ food_table.py       # 食材营养与价格表
│  │  ├─ config.py              # pydantic-settings 配置
│  │  ├─ database.py            # SQLAlchemy 引擎 / Session
│  │  ├─ models.py              # diet_records 表
│  │  ├─ schemas.py             # 请求 / 响应 / 食谱 JSON 结构
│  │  └─ main.py                # FastAPI 应用与路由
│  ├─ tests/                    # 22 个单元测试
│  ├─ Dockerfile
│  ├─ requirements.txt          # 镜像构建用（锁版本）
│  └─ pyproject.toml            # 本地开发（uv）
└─ frontend/                    # 前端
   ├─ src/
   │  ├─ App.vue                # 表单 + 历史列表
   │  ├─ components/PlanView.vue# 食谱详情与图表
   │  └─ api.js
   ├─ nginx.conf                # SPA 路由 + /api、/health 反代
   ├─ Dockerfile
   └─ vite.config.js
```

## 测试

```bash
cd service
uv sync
uv run pytest -q        # 22 passed
```

测试通过 `tests/conftest.py` 强制 `LLM_PROVIDER=mock`，不会请求真实模型，也不依赖本地 `.env` 中的密钥。

## License

[MIT](LICENSE)
