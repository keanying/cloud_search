"""国内外常见大模型供应方预设。全部走 OpenAI 兼容 Chat Completions 接口。

模型名仅作填写示例（供应方会更新型号），以管理后台实际配置为准；能力矩阵须按供应方文档勾选。
"""

from __future__ import annotations

PROVIDER_PRESETS: list[dict] = [
    {"provider_type": "openai", "provider_name": "OpenAI", "base_url": "https://api.openai.com/v1",
     "example_models": ["gpt-4.1", "gpt-4.1-mini"], "note": None},
    {"provider_type": "deepseek", "provider_name": "DeepSeek", "base_url": "https://api.deepseek.com",
     "example_models": ["deepseek-chat", "deepseek-reasoner"],
     "note": "推理模型的工具调用/JSON能力以官方文档为准，不支持时取消勾选，系统会改用提示词约束输出"},
    {"provider_type": "moonshot", "provider_name": "Kimi（月之暗面）", "base_url": "https://api.moonshot.cn/v1",
     "example_models": ["kimi-k2-0905-preview", "moonshot-v1-128k"], "note": None},
    {"provider_type": "volcengine", "provider_name": "火山方舟（豆包）", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "example_models": ["<推理接入点ID ep-xxxx 或模型ID>"], "note": "模型名可填写方舟控制台的推理接入点ID"},
    {"provider_type": "dashscope", "provider_name": "通义千问（阿里云百炼）",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "example_models": ["qwen-plus", "qwen-max"],
     "note": None},
    {"provider_type": "zhipu", "provider_name": "智谱", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "example_models": ["glm-4-plus", "glm-4-flash"], "note": None},
    {"provider_type": "openai_compatible", "provider_name": "自定义（OpenAI兼容）", "base_url": "http://127.0.0.1:8001/v1",
     "example_models": [], "note": "vLLM / Ollama / 其他兼容网关"},
]
