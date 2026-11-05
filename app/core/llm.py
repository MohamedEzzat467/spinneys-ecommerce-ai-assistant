# -*- coding: utf-8 -*-
"""
app/core/llm.py
===============
Groq LLM Client Interface for Spinneys Conversational Shopping Assistant.

Manages connections to Groq's inference API using the official `groq` SDK.
Enforces:
  • Default model: llama-3.1-8b-instant
  • Temperature: 0.0 (deterministic parsing)
  • Structured JSON response format
  • Token usage tracking (prompt, completion, total)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Ensure .env is loaded
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("spinneys.llm")

DEFAULT_MODEL = os.getenv("LLM_PARSER_MODEL", "llama-3.1-8b-instant")


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: dict[str, Any]
    raw_response: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0


class GroqClient:
    """Wrapper around the official Groq SDK client."""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        self.default_model = default_model or DEFAULT_MODEL
        self._client = None
        self._working_model: Optional[str] = None

        if self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
                log.info("Groq client initialized with model %s", self.default_model)
            except Exception as e:
                log.warning("Could not initialize Groq client: %s", e)
        else:
            log.info("No GROQ_API_KEY detected in environment. Hybrid parser will rely on deterministic rules.")

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(self.api_key)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """
        Execute chat completion expecting a JSON object output.
        """
        if not self.is_available:
            raise RuntimeError("Groq client is not available (missing GROQ_API_KEY).")

        import time
        model_name = model or self._working_model or self.default_model
        t0 = time.perf_counter()

        models_to_try = []
        if self._working_model and self._working_model not in models_to_try:
            models_to_try.append(self._working_model)
        for cand in [model_name, "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if cand and cand not in models_to_try:
                models_to_try.append(cand)

        last_err = None
        response = None
        used_model = model_name

        for m in models_to_try:
            try:
                response = self._client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                used_model = m
                self._working_model = m
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "model_not_found" in err_str or "does not exist" in err_str or "404" in err_str or "decommissioned" in err_str or "429" in err_str or "rate_limit" in err_str:
                    continue
                raise e

        if response is None:
            raise last_err

        latency = (time.perf_counter() - t0) * 1000.0

        raw_text = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse LLM JSON output: %s | Raw: %s", exc, raw_text)
            parsed = {}

        usage = TokenUsage()
        if hasattr(response, "usage") and response.usage:
            usage.prompt_tokens = getattr(response.usage, "prompt_tokens", 0)
            usage.completion_tokens = getattr(response.usage, "completion_tokens", 0)
            usage.total_tokens = getattr(response.usage, "total_tokens", 0)

        return LLMResponse(
            content=parsed,
            raw_response=raw_text,
            model=used_model,
            usage=usage,
            latency_ms=latency,
        )

    def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        """
        Execute chat completion returning natural conversational text output.
        """
        if not self.is_available:
            raise RuntimeError("Groq client is not available (missing GROQ_API_KEY).")

        model_name = model or self._working_model or self.default_model

        models_to_try = []
        if self._working_model and self._working_model not in models_to_try:
            models_to_try.append(self._working_model)
        for cand in [model_name, "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            if cand and cand not in models_to_try:
                models_to_try.append(cand)

        last_err = None
        for m in models_to_try:
            try:
                response = self._client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._working_model = m
                return response.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "model_not_found" in err_str or "does not exist" in err_str or "404" in err_str or "decommissioned" in err_str or "429" in err_str or "rate_limit" in err_str:
                    continue
                raise e

        raise last_err


# Global singleton instance
_llm_client: Optional[GroqClient] = None


def get_llm_client() -> GroqClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = GroqClient()
    return _llm_client
