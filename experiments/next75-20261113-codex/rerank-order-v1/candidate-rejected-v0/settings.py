"""Run configuration. Address, key and model identifier come only from the environment."""
from dataclasses import dataclass, field
import math
import os
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


def env_first(*names, default="", environ=None):
    env = os.environ if environ is None else environ
    for name in names:
        value = env.get(name, "").strip()
        if value and value != name:
            return value
    return default


def tolerant(name, default, lower, upper=None, kind=int, environ=None):
    """Optional numeric setting: a malformed or out-of-range value never aborts the batch."""
    raw = env_first(name, default=str(default), environ=environ)
    try:
        value = kind(raw)
        if not math.isfinite(value):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return default
    if upper is None:
        return value if value >= lower else default
    return max(lower, min(upper, value))


def choice(name, default, allowed, environ=None):
    value = env_first(name, default=default, environ=environ).lower()
    return value if value in allowed else default


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    temperature: float = 0.0
    max_tokens: int = 2048          # value configured by the platform (MAX_TOKENS)
    workers: int = 3
    timeout: float = 150.0
    attempts: int = 3
    top_k: int = 12                 # platform TOP_K; used by the A2 control mode only
    context_chars: int = 32000      # A2 control mode cap
    runtime_seconds: float = 1120.0
    # --- N1 factors (each one is switchable for single-factor comparisons) ---
    prompt: str = "n1"              # n1 | a2
    context: str = "docs"           # full | docs | wide | a2 (large contexts step down automatically)
    reasoning: str = "default"      # default | low | medium | off
    max_tokens_floor: int = 4096    # 0 = send exactly the platform value
    rescue: bool = True             # recover truncated/empty generations instead of a stub
    fewshot: bool = True
    wide_k: int = 10
    wide_chars: int = 14000
    doc_count: int = 2              # whole documents in the "docs" context
    doc_k: int = 8
    doc_chars: int = 60000
    control: bool = False           # exact A2 behaviour
    big_timeout: float = 100.0      # per-call limit for the large contexts before stepping down
    # --- N2 additions ---
    retry_tokens: int = 8192        # budget of the second try in the same context (0 = no such try)
    retry_reasoning: str = "low"    # reasoning hint of that second try: low | medium | default | off
    think_temperature: float = -1.0  # sampling of thinking generations; negative = platform TEMPERATURE
    think_top_p: float = -1.0        # negative = not sent
    style: str = "n1"               # answer-length wording of the prompt: n1 | brief
    workers_cap: int = 8            # parallel rows may grow to this number when the time budget requires it
    quick: bool = False             # compact context, no reasoning, for every row (the former time-saving mode)

    @property
    def main_max_tokens(self):
        return max(self.max_tokens, self.max_tokens_floor)

    @classmethod
    def from_env(cls, environ=None):
        def get(*keys, default=""):
            return env_first(*keys, default=default, environ=environ)

        def num(key, default, lo, hi=None, kind=int):
            return tolerant(key, default, lo, hi, kind, environ)

        base = get("LLM_BASE_URL", "OPENAI_BASE_URL", "BASE_URL").rstrip("/")
        key = get("LLM_API_KEY", "OPENAI_API_KEY")
        model = get("LLM_MODEL", "OPENAI_MODEL", "GEN_MODEL")
        if not base or not key or not model:
            missing = [label for label, value in (
                ("LLM_BASE_URL/OPENAI_BASE_URL/BASE_URL", base),
                ("LLM_API_KEY/OPENAI_API_KEY", key),
                ("LLM_MODEL/OPENAI_MODEL/GEN_MODEL", model)) if not value]
            raise ConfigurationError("Missing configuration: " + ", ".join(missing))
        parts = urlsplit(base)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ConfigurationError("LLM_BASE_URL: expected HTTP(S) URL without credentials/query")
        if any(c in key for c in "\r\n"):
            raise ConfigurationError("LLM_API_KEY: invalid header characters")
        # N1_CONTROL=1 reproduces the protected A2 baseline exactly (for paired comparisons).
        control = env_first("N1_CONTROL", default="0", environ=environ) in ("1", "true", "yes")
        flag = lambda name, default: env_first(name, default="1" if default else "0", environ=environ) not in ("0", "false", "no")
        return cls(
            base, key, model,
            num("TEMPERATURE", 0.0, 0.0, 2.0, float),
            num("MAX_TOKENS", 2048, 1),
            num("MAX_WORKERS", 3, 1, 8),
            num("LLM_TIMEOUT", 90.0 if control else cls.timeout, 1.0, 180.0 if control else 900.0, float),
            num("LLM_ATTEMPTS", 3, 1, 4),
            num("TOP_K", 12, 1, 40),
            num("CONTEXT_CHARS", 32000, 4000, 90000),
            num("RUN_BUDGET_SECONDS", 1120.0, 1.0, 1140.0, float),
            "a2" if control else choice("N1_PROMPT", cls.prompt, ("n1", "a2"), environ),
            "a2" if control else choice("N1_CONTEXT", cls.context, ("full", "docs", "wide", "a2"), environ),
            "default" if control else choice("N1_REASONING", cls.reasoning, ("default", "low", "medium", "off"), environ),
            0 if control else num("N1_MAX_TOKENS_FLOOR", cls.max_tokens_floor, 0, 16384),
            False if control else flag("N1_RESCUE", cls.rescue),
            flag("N1_FEWSHOT", cls.fewshot),
            num("N1_WIDE_K", cls.wide_k, 1, 40),
            num("N1_WIDE_CHARS", cls.wide_chars, 2000, 60000),
            num("N1_DOC_COUNT", cls.doc_count, 1, 6),
            num("N1_DOC_K", cls.doc_k, 0, 40),
            num("N1_DOC_CHARS", cls.doc_chars, 8000, 120000),
            control,
            num("N1_BIG_TIMEOUT", cls.big_timeout, 5.0, 900.0, float),
            0 if control else num("N2_RETRY_TOKENS", cls.retry_tokens, 0, 16384),
            choice("N2_RETRY_REASONING", cls.retry_reasoning, ("low", "medium", "default", "off"), environ),
            -1.0 if control else num("N2_THINK_TEMPERATURE", cls.think_temperature, -1.0, 2.0, float),
            -1.0 if control else num("N2_THINK_TOP_P", cls.think_top_p, -1.0, 1.0, float),
            "n1" if control else choice("N2_STYLE", cls.style, ("n1", "brief"), environ),
            num("N2_WORKERS_CAP", cls.workers_cap, 1, 8),
            False if control else flag("N2_QUICK", cls.quick))
