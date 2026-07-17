"""Pinned AI provider capabilities; no runtime-supplied endpoints are accepted."""

from dataclasses import dataclass
from enum import StrEnum


class ProviderCode(StrEnum):
    DEEPSEEK = "deepseek"
    GLM = "glm"
    QIANWEN = "qianwen"
    MOCK = "mock"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    code: ProviderCode
    base_url: str
    request_path: str
    models: tuple[str, ...]
    real_call_enabled: bool
    supports_thinking_disabled: bool


_CATALOG = {
    ProviderCode.DEEPSEEK: ProviderCapability(
        code=ProviderCode.DEEPSEEK,
        base_url="https://api.deepseek.com",
        request_path="/chat/completions",
        models=("deepseek-v4-flash",),
        real_call_enabled=True,
        supports_thinking_disabled=True,
    ),
    ProviderCode.GLM: ProviderCapability(
        code=ProviderCode.GLM,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        request_path="/chat/completions",
        models=("glm-5.2",),
        real_call_enabled=False,
        supports_thinking_disabled=False,
    ),
    ProviderCode.QIANWEN: ProviderCapability(
        code=ProviderCode.QIANWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        request_path="/chat/completions",
        models=("qwen-flash",),
        real_call_enabled=False,
        supports_thinking_disabled=False,
    ),
    ProviderCode.MOCK: ProviderCapability(
        code=ProviderCode.MOCK,
        base_url="http://model-gateway.invalid",
        request_path="/chat/completions",
        models=("mock-v1",),
        real_call_enabled=False,
        supports_thinking_disabled=False,
    ),
}


def provider_capability(code: ProviderCode) -> ProviderCapability:
    return _CATALOG[code]


def provider_catalog() -> tuple[ProviderCapability, ...]:
    return tuple(_CATALOG.values())
