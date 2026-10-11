from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from supportkit.config import load_platform
from supportkit.llm import OPENAI_COMPAT, parse_spec

LITELLM_PREFIX = {
    "ollama": "ollama_chat",
    "anthropic": "anthropic",
    "openai": "openai",
    "groq": "groq",
    "deepseek": "deepseek",
    "openrouter": "openrouter",
    "custom": "openai",
}


def ollama_host() -> str:
    cfg = load_platform().llm.get("providers", {}).get("ollama", {}) or {}
    return (cfg.get("host") or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")


def openai_compat(provider: str) -> Tuple[str, str]:
    base_env, base_default, key_env = OPENAI_COMPAT[provider]
    return os.environ.get(base_env, base_default), os.environ.get(key_env, "") or "not-needed"


def litellm_target(spec: str) -> Tuple[str, Optional[str]]:
    provider, model = parse_spec(spec)
    if provider not in LITELLM_PREFIX:
        raise ValueError(f"provider '{provider}' has no LiteLLM mapping")
    name = f"{LITELLM_PREFIX[provider]}/{model}"
    if provider == "ollama":
        return name, ollama_host()
    if provider == "custom":
        return name, openai_compat("custom")[0]
    return name, None


def crewai_llm(spec: str, temperature: float):
    from crewai import LLM

    name, base = litellm_target(spec)
    kwargs: Dict[str, object] = {"model": name, "temperature": temperature}
    if base:
        kwargs["base_url"] = base
    return LLM(**kwargs)


def adk_model(spec: str):
    from google.adk.models.lite_llm import LiteLlm

    name, base = litellm_target(spec)
    return LiteLlm(model=name, api_base=base) if base else LiteLlm(model=name)


def strands_model(spec: str, temperature: float, max_tokens: int = 700):
    provider, model = parse_spec(spec)
    if provider == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(host=ollama_host(), model_id=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        return AnthropicModel(model_id=model, max_tokens=max_tokens, params={"temperature": temperature})
    if provider in OPENAI_COMPAT:
        from strands.models.openai import OpenAIModel

        base, key = openai_compat(provider)
        return OpenAIModel(client_args={"api_key": key, "base_url": base}, model_id=model, params={"temperature": temperature, "max_tokens": max_tokens})
    raise ValueError(f"provider '{provider}' is not supported by Strands here")


def pydantic_ai_model(spec: str):
    provider, model = parse_spec(spec)
    if provider == "ollama":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        return OpenAIChatModel(model, provider=OllamaProvider(base_url=f"{ollama_host()}/v1"))
    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel

        return AnthropicModel(model)
    if provider in OPENAI_COMPAT:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        base, key = openai_compat(provider)
        return OpenAIChatModel(model, provider=OpenAIProvider(base_url=base, api_key=key))
    raise ValueError(f"provider '{provider}' is not supported by Pydantic AI here")
