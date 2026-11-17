# -*- coding: utf-8 -*-
"""GLM 客户端封装（智谱开放平台 OpenAI 兼容接口，T2.3）。
只负责「调 LLM 拿文本」这一件事：不配 Key / 超时 / 报错一律返回 None，
由调用方（rules.parse_intent 等）降级到本地规则实现（R16 熔断降级）。
用 httpx 直连（不引入 openai SDK，保持依赖最小）。"""
import json

import httpx

from ..config import GLM_API_KEY, GLM_BASE_URL, GLM_MODEL, GLM_TIMEOUT


def glm_available() -> bool:
    """是否配置了真实 GLM Key（未配置时调用方直接走 Demo 规则）。"""
    return bool(GLM_API_KEY)


def glm_chat(prompt: str, system: str, temperature: float = 0.1) -> str | None:
    """调用 GLM chat/completions，返回模型文本；失败返回 None（调用方降级）。
    temperature 默认 0.1：槽位抽取/分级任务要稳定输出，不要发散。"""
    if not GLM_API_KEY:
        return None
    try:
        r = httpx.post(
            GLM_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + GLM_API_KEY},
            json={
                "model": GLM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
            timeout=GLM_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def glm_chat_json(prompt: str, system: str, temperature: float = 0.1) -> dict | None:
    """glm_chat + JSON 提取：模型可能裹 ```json 代码栏或夹带说明文字，
    这里宽容解析出第一个 JSON 对象；解析失败返回 None。"""
    text = glm_chat(prompt, system, temperature)
    if text is None:
        return None
    # 去掉 ```json ... ``` 围栏
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    # 截取第一个 { 到最后一个 }
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None
