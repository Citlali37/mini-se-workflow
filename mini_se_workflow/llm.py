from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Raised when a model request or response is invalid."""


class WorkflowLLMClient(Protocol):
    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]: ...


class DeepSeekClient:
    """Small dependency-free client for DeepSeek's Chat Completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 60,
        max_retries: int = 3,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        request_limit: int | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("LLM_BASE_URL 不能为空。")
        if not api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY 不能为空。")
        if not model.strip():
            raise ValueError("LLM_MODEL 不能为空。")
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.thinking = thinking or None
        self.reasoning_effort = reasoning_effort or None
        self.max_tokens = max_tokens
        self.request_limit = request_limit
        self.request_count = 0
        self.usage_records: list[dict] = []

    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        if self.thinking:
            payload["thinking"] = {"type": self.thinking}
            payload.pop("temperature", None)
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            if self.request_limit is not None and self.request_count >= self.request_limit:
                raise LLMError("已达到本次评测请求预算，停止模型调用。")
            self.request_count += 1
            request = urllib.request.Request(
                self.url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                self.usage_records.append({"agent": agent_name, "model": response_data.get("model", self.model),
                    "usage": response_data.get("usage", {}), "request_number": self.request_count,
                    "finish_reason": response_data.get("choices", [{}])[0].get("finish_reason") if response_data.get("choices") else None})
                content = self._extract_content(response_data)
                return parse_json_object(content)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = LLMError(f"DeepSeek 返回 HTTP {exc.code}：{detail}")
                if exc.code != 429 and exc.code < 500:
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = LLMError(f"DeepSeek 请求失败：{exc}")
            except LLMError as exc:
                last_error = exc
                break

            if attempt + 1 < self.max_retries:
                time.sleep(0.5 * (2**attempt))
        raise last_error or LLMError("DeepSeek 请求失败。")

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek 响应缺少 choices[0].message.content。") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("DeepSeek 没有返回有效内容。")
        return content


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (json.JSONDecodeError, ValueError):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("模型输出不是有效的 JSON 对象。")
        try:
            value = json.loads(text[start : end + 1], parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError("模型输出不是有效的 JSON 对象。") from exc
    if not isinstance(value, dict):
        raise LLMError("模型输出必须是 JSON 对象。")
    return value

