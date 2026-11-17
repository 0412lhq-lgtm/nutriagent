"""pytest 全局配置：在导入 app 之前固定环境变量。

环境变量的优先级高于 .env，所以这里把 LLM_PROVIDER 锁成 mock，
测试永远不会请求真实 DeepSeek，也不依赖本地 .env 里的密钥。
"""

import os

# LLM 固定为 mock，避免测试发出真实请求、消耗 token
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ.setdefault("LLM_BASE_URL", "https://api.deepseek.com")
os.environ.setdefault("LLM_MODEL", "deepseek-chat")
os.environ.setdefault("LLM_TIMEOUT", "150")

# 单元测试不连真实数据库，提供占位值满足配置校验
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_DB", "nutri_agent_test")
os.environ.setdefault("MAX_RETRIES", "2")
