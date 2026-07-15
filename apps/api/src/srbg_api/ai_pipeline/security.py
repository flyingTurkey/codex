"""Deterministic prompt-injection pre-scan for untrusted document text."""

import re
from dataclasses import dataclass
from typing import ClassVar, Literal


@dataclass(frozen=True, slots=True)
class InjectionScanResult:
    detected: bool
    risk_level: Literal["R1", "R4"]
    patterns: frozenset[str]
    scanner_version: str


class PromptInjectionScanner:
    version = "prompt-injection-scanner-1.0.0"
    _PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "IGNORE_INSTRUCTIONS": re.compile(
            r"(?:忽略|无视|绕过).{0,12}(?:之前|以上|系统|指令|规则)|ignore.{0,16}instructions?",
            re.IGNORECASE,
        ),
        "SECRET_EXFILTRATION": re.compile(
            r"(?:泄露|输出|发送|提取).{0,12}(?:密钥|令牌|密码|cookie|提示词)|"
            r"(?:reveal|exfiltrate|leak).{0,16}(?:secret|token|password|prompt)",
            re.IGNORECASE,
        ),
        "TOOL_INVOCATION": re.compile(
            r"(?:调用|执行|运行).{0,12}(?:工具|命令|shell|sql)|"
            r"(?:call|invoke|run).{0,12}(?:tool|command|shell|sql)",
            re.IGNORECASE,
        ),
        "ROLE_OVERRIDE": re.compile(
            r"(?:你现在是|扮演|切换为).{0,20}(?:管理员|系统|开发者)|"
            r"you are now.{0,20}(?:admin|system|developer)",
            re.IGNORECASE,
        ),
    }

    def scan(self, text: str) -> InjectionScanResult:
        matches = frozenset(
            name for name, pattern in self._PATTERNS.items() if pattern.search(text)
        )
        detected = bool(matches)
        return InjectionScanResult(
            detected=detected,
            risk_level="R4" if detected else "R1",
            patterns=matches,
            scanner_version=self.version,
        )
