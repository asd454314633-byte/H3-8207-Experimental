"""V28 Director - LAYER 1 provider contract (task section 10).

The UI and the state machine only ever talk to `DirectorProvider`. Nothing in
this package may import a Bonsai-specific symbol except `v28_bonsai_provider.py`
and `v28_mock_provider.py`. That is what keeps "today Bonsai, tomorrow Qwen /
OpenAI / Gemma" a configuration change rather than a rewrite.

Provider-agnostic rules that belong here, not in the Bonsai class:
  * JSON-only contract plus the bounded repair loop (task section 34: at most 2
    repairs, then keep the raw response and raise - never mutate project state).
  * Per-task thinking / token / timeout budgets (task section 33: unlimited
    thinking is forbidden; a timeout must preserve the caller's input).
"""
from __future__ import annotations

import abc
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import v28_paths as P
from . import v28_schemas as S

# --- task section 33: explicit ceilings, by kind of work -----------------
# P11 TEST3 rewrote this table, and it rewrote the comment too. Two things were
# wrong with the old one:
#
#  1. "thinking" was *advisory*, which in practice meant dead. Nothing in the
#     code path ever carried it to llama.cpp, and the reasoning tier is a
#     command-line flag there (`--reasoning-budget`), not a request field -
#     measured: per-request `reasoning_budget` / `chat_template_kwargs.reasoning`
#     / `thinking` all returned byte-identical replies. So analyze_references
#     believed it was asking for 512 thinking tokens while the resident server
#     was running 2048. It is binding now: _json_only() -> ensure_tier().
#  2. The ceilings were not compatible with the model's measured speed, so the
#     first real call could not finish even with a perfect provider. From the
#     P11 receipts: decode 10.1-11.1 tok/s at ~2.4k context, prefill
#     61.18 tok/s (2,355 tokens = 38.5 s for ONE reference image, ~8.3k tokens
#     = ~136 s for the four the product allows). Sizing rule now:
#         timeout_s >= 4-image prefill + max_tokens / 10 tok/s, with margin
#         max_tokens - tier_budget >= MIN_ANSWER_TOKENS   (a reply must fit
#         alongside its own thinking, or `content` comes back empty)
#     The old analyze row was 2048 max_tokens against a 2048-token tier and a
#     240 s clock: 38.5 s prefill + 2048/10.5 s = 234 s, i.e. the budget expired
#     in the same second the thinking budget did, before one answer token.
MIN_ANSWER_TOKENS = 1024     # headroom required above the tier's thinking budget
BUDGET: dict[str, dict[str, Any]] = {
    "analyze_references": {"thinking": "low",    "max_tokens": 2048, "timeout_s": 600},
    "plan_story":         {"thinking": "medium", "max_tokens": 9000, "timeout_s": 1500},
    "compile_segment":    {"thinking": "low",    "max_tokens": 2560, "timeout_s": 600},
    "replan_tail":        {"thinking": "medium", "max_tokens": 9000, "timeout_s": 1500},
    # Gate-8B: a targeted fill writes ONE existing segment's semantic fields, so it
    # must not inherit plan_story's 9000-token / 1500 s ceiling - six of those
    # would be slower than the whole-plan rewrite this mechanism replaced.
    "segment_repair":     {"thinking": "low",    "max_tokens": 2048, "timeout_s": 400},
}
REPAIR_ATTEMPTS = 2          # section 34: "自动做最多2次repair"
HARD_REPAIR_ATTEMPTS = 3     # absolute ceiling if a caller asks for more
# Gate-8B: fills are segment-local, but they still cost a model call each. Cap both
# the per-segment retries and the per-run total so a degraded reply degrades into a
# bounded failure instead of a six-way rewrite by another name.
TARGETED_REPAIR_ATTEMPTS_PER_SEGMENT = 2
MAX_TARGETED_REPAIR_CALLS = 4


class DirectorError(Exception):
    """Anything the caller is allowed to surface as a Chinese message."""


class DirectorUnavailable(DirectorError):
    """Provider not started / executable missing / health check failed."""


class BudgetExceeded(DirectorError):
    """Section 33: timeout hit. Input stays with the caller so retry is safe."""

    def __init__(self, kind: str, timeout_s: float, partial: str = ""):
        self.kind = kind
        self.timeout_s = float(timeout_s)
        self.partial = partial
        super().__init__(f"{kind} exceeded {timeout_s}s budget")


class SchemaRepairFailed(DirectorError):
    """Section 34 final failure: raw responses are kept, project state untouched."""

    def __init__(self, kind: str, errors: list[str], raws: list[str], *, repair_count: int | None = None):
        self.kind = kind
        self.errors = list(errors)
        self.raws = list(raws)
        self.repair_count = max(0, len(raws) - 1) if repair_count is None else repair_count
        super().__init__(f"{kind} still invalid after {self.repair_count} repairs: "
                         + "; ".join(self.errors[:6]))


@dataclass
class Health:
    ok: bool
    provider: str
    running: bool = False
    detail: str = ""
    model: str = ""
    endpoint: str = ""
    vision: bool = False
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "provider": self.provider, "running": self.running,
                "detail": self.detail, "model": self.model, "endpoint": self.endpoint,
                "vision": self.vision, "extra": self.extra}


# --- the contract ---------------------------------------------------------
class DirectorProvider(abc.ABC):
    """Six methods, exactly as the task specifies. Nothing else is public API."""

    name: str = "abstract"
    SUPPORTS_VISION: bool = False

    # lifecycle -----------------------------------------------------------
    def start(self) -> None:
        """Bring the model up. Must be idempotent."""

    def stop(self) -> None:
        """Bring the model down and confirm release. Must be idempotent."""

    @abc.abstractmethod
    def health(self) -> Health:
        ...

    # the three director operations ---------------------------------------
    @abc.abstractmethod
    def analyze_references(self, images: list[dict], *, brief: str = "") -> dict:
        """-> REFERENCE_PROFILE (validated). `images` = [{index,picture,path,b64,mime,name}]"""

    @abc.abstractmethod
    def plan_story(self, *, story_goal: str, profile: dict, total_seconds: float,
                   segment_seconds: float, style: str = "auto",
                   continuation_mode: str = "same_shot",
                   expect_segments: int | None = None) -> dict:
        """-> STORY_PLAN (validated). One shot == one segment."""

    @abc.abstractmethod
    def compile_segment(self, *, plan: dict, segment_id: int, profile: dict,
                        override_beat: str = "") -> str:
        """-> the final H3 prompt text for exactly one segment."""

    # the only thing a subclass must really implement ----------------------
    @abc.abstractmethod
    def _complete(self, messages: list[dict], *, max_tokens: int,
                  timeout_s: float, temperature: float) -> str:
        """Return raw assistant text. Raises DirectorUnavailable / BudgetExceeded."""

    # ------------------------------------------------------------- helpers
    def ensure_tier(self, thinking: str | None) -> None:
        """Bring the provider up at exactly this reasoning tier, restarting if needed.

        Default no-op: a provider with no reasoning budget has nothing to honour.
        Bonsai2 overrides it because its tier is a command-line flag that cannot be
        set per request (P11 TEST3). Called from _json_only(), so the tier a kind
        declares is the tier the model actually runs with.
        """

    def budget_for(self, kind: str) -> dict:
        b = BUDGET.get(kind)
        if not b:
            raise KeyError(f"unknown director op kind {kind!r}")
        return dict(b)

    def _json_only(self, messages: list[dict], *, kind: str,
                   validate: Callable[[Any], list[str]],
                   normalize: Callable[[Any], Any] | None = None,
                   temperature: float = 0.7,
                   raw_log: Callable[[str], None] | None = None) -> Any:
        """Ask for JSON, repair at most REPAIR_ATTEMPTS times, never pass prose on.

        `messages` is never mutated in place: the caller's input survives every
        failure path, which is what makes section 33's "超时保留输入，允许重试" true.
        """
        b = self.budget_for(kind)
        # Bind the declared tier before the first token is asked for. A repair turn
        # reuses the same tier - it must not silently upgrade mid-conversation.
        self.ensure_tier(b.get("thinking"))
        attempts = max(0, min(REPAIR_ATTEMPTS, HARD_REPAIR_ATTEMPTS))
        raws: list[str] = []
        errors: list[str] = []
        convo = list(messages)
        for attempt in range(attempts + 1):
            text = self._complete(convo, max_tokens=b["max_tokens"],
                                  timeout_s=b["timeout_s"], temperature=temperature)
            raws.append(text)
            if raw_log:
                try:
                    raw_log(text)
                except Exception:      # logging must never lose the caller's result
                    pass
            try:
                obj = S.extract_json(text)
            except ValueError as exc:
                errors = [f"reply was not JSON ({exc})"]
                if attempt >= attempts:
                    break
                convo = list(messages) + _repair_turn(text, errors)
                continue
            if normalize:
                try:
                    obj = normalize(obj)
                except Exception as exc:
                    errors = [f"normalisation failed: {type(exc).__name__}: {exc}"]
                    if attempt >= attempts:
                        break
                    convo = list(messages) + _repair_turn(text, errors)
                    continue
            try:
                errors = validate(obj) or []
            except Exception as exc:
                # A validator that raises is still "校验失败", not a crash. Left
                # uncaught it would escape _json_only as a bare TypeError, skip the
                # SchemaRepairFailed path, and therefore skip the caller's
                # _stash_raw() - losing the raw response §34 requires us to keep.
                errors = [f"validator raised {type(exc).__name__}: {exc}"]
            if not errors:
                return obj
            if attempt >= attempts:
                break
            convo = list(messages) + _repair_turn(text, errors)
        raise SchemaRepairFailed(kind, errors, raws)


def _repair_turn(previous: str, errors: list[str]) -> list[dict]:
    """Feed back only the paths that broke, not the whole reply (keeps tokens down)."""
    quoted = previous if len(previous) <= 1200 else previous[:1200] + " ...[truncated]"
    return [
        {"role": "assistant", "content": quoted},
        {"role": "user", "content":
            "你的上一次回复没有通过结构校验。只输出修正后的 JSON，"
            "不要解释、不要 Markdown 代码块、不要任何前后缀文字。\n必须修好的问题：\n"
            + "\n".join(f"- {e}" for e in errors[:12])},
    ]


# --- registry: section 10's "不得绑死" made structural ---------------------
_REGISTRY: dict[str, type[DirectorProvider]] = {}


def register(cls: type[DirectorProvider]) -> type[DirectorProvider]:
    if not getattr(cls, "name", "") or cls.name == "abstract":
        raise ValueError(f"{cls.__name__} needs a unique `name`")
    _REGISTRY[cls.name] = cls
    return cls


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def _instantiate(name: str) -> DirectorProvider:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise DirectorUnavailable(
            f"未知的导演提供方 {name!r}；可用: {available_providers()}")
    return cls()


def get_provider(name: str | None = None) -> DirectorProvider:
    """Resolve once per call site. Defaults to env, then to the first registered."""
    want = (name or P.os.environ.get("H3_V28_DIRECTOR", "") or "").strip()
    if not want:
        want = "gemma4" if "gemma4" in _REGISTRY else (available_providers() or [""])[0]
    if not want:
        raise DirectorUnavailable("没有任何已注册的 DirectorProvider")
    return _instantiate(want)


# --- small shared utilities used by several providers ---------------------
_IMG_NAME_RE = re.compile(r"[\\\/*?\"<>|:]")


def safe_picture_label(index: int, filename: str) -> str:
    return f"<Picture {int(index)}> ({_IMG_NAME_RE.sub('_', str(filename))[:80]})"


def utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def dump_preview(obj: Any, limit: int = 900) -> str:
    try:
        t = json.dumps(obj, ensure_ascii=False)
    except Exception:
        t = str(obj)
    return t if len(t) <= limit else t[:limit] + "..."
