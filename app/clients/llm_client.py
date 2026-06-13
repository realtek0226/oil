from __future__ import annotations

import json
from typing import Any

import requests
from requests import HTTPError

from app.core.settings import LlmSettings


class LlmClient:
    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.base_url and self.settings.api_key and self.settings.model_name)

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("LLM is not configured.")
        user_context = user_context or {}
        isolation_prompt = (
            "本次调用是一次独立请求。只能使用本次 messages 中提供的信息，"
            "不得引用任何历史对话、其他用户上下文、浏览器本地历史或服务端缓存。"
            "如果需要使用外部信息但当前接口没有提供，请明确说明不确定，不要编造。"
        )
        scoped_messages = [{"role": "system", "content": isolation_prompt}, *messages]
        body: dict[str, Any] = {
            "model": self.settings.model_name,
            "temperature": 0,
            "messages": scoped_messages,
        }
        if response_format is not None:
            body["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        if request_id:
            headers["X-Oil-Research-Request-Id"] = request_id[:128]
        if user_context.get("user_id") is not None:
            headers["X-Oil-Research-User-Id"] = str(user_context["user_id"])[:64]
        response = requests.post(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=body,
            timeout=self.settings.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except HTTPError as exc:
            raise RuntimeError(self._format_error(response)) from exc
        payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()

    def summarize(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> str:
        return self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            request_id=request_id,
            user_context=user_context,
        )

    def summarize_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            request_id=request_id,
            user_context=user_context,
        )
        return json.loads(content)

    def _format_error(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        message = ""
        if isinstance(payload, dict):
            error = payload.get("error") or payload
            if isinstance(error, dict):
                message = str(error.get("message") or error.get("detail") or "")
            else:
                message = str(error or "")
        if not message:
            message = response.text[:300]
        if response.status_code == 403 and "无权访问模型" in message:
            return f"当前 API Key 无权访问配置模型 {self.settings.model_name}，请在配置中切换到有权限的模型。"
        return f"LLM 调用失败（HTTP {response.status_code}）：{message}"
