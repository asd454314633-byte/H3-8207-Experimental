"""CPU 中英翻译引擎：确定性术语分片 + 孤立单字守卫 + 离线 MT（Argos）。

## 定稿架构（由本机对照实验决定，证据见 `_evidence/g3_translation/`）

    中文输入
      → ① 受保护片段（参考标签 / 说话人 ID / 镜头标签 / 时间戳 / 角色名）→ 原样保留
      → ② 受控术语（官方镜头词汇 / 动作 / 方位 / 身体部位 / 否定 / 时序 / 场景 / 外观）
           → 确定性英文（最长匹配）
      → ③ 其余**含汉字且长度 ≥2** 的片段 → 送 Argos（CPU）翻译
      → ④ **孤立单字** → 查 CHAR_TERMS；未收录则丢弃并计数（绝不送 MT）
      → ⑤ 无汉字片段 → 不送 MT，原样拼接
      → ⑥ 标点归一（跳过 <d> 台词块）→ 英文

## 为什么这样做（实验证据，全部为本机实测）

| 现象 | 实测结果 | 结论 |
|---|---|---|
| Argos 对纯标点输入 | `translate("，") == "I don't know."` | 绝不把无汉字片段单独送 MT |
| Argos 对孤立单字 | `的`→"Yes."、`之`→"Shit."、`到`→"Present."、`给`→"Here." | 孤立单字必须确定性处理或丢弃 |
| Argos 对 ≥2 字词/短语 | `便利店`→"A convenience store."、`门口`→"The door." | 2 字以上可安全送 MT |
| Argos 对复合名词短语 | `深夜的便利店`→"Late at night."（**丢掉"便利店"**） | 实体丢失 → 场景/外观词必须进术语表 |
| 括号类占位符 | `⟦0⟧` 被吞、`«0»` 变 `♪`、`ZZ0ZZ` 截成 `ZZ0Z` | 不能用符号/重复字母做占位符 |
| 整句 + 生造词占位符 | 长句劣化（`女孩用左手拿起桌上的杯子` → "The girl uses a cup on the left hand picks up table and also outside the gazes at window."） | 不作主路径 |
| 分片模式 | 实体与方位保全更好（同句 → "Girls left hand picks up the glass on the table, at the same time gazes at outside the window."） | **定为主路径** |

整句占位符路径（`_whole_sentence`）**保留但不再使用**，只为 A/B 对照可复现。

本模块**不翻译中文台词**：台词由编译器的 `<d>` 通道逐字保留，不进入本模块。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from . import glossary

# ---------------------------------------------------------------------------
# 占位符
# ---------------------------------------------------------------------------
_PSEUDO_PREFIX = "Zorb"
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def pseudo_word(index: int) -> str:
    """生成一个可被 MT 原样透传的生造词：Zorbaa、Zorbab、…（676 个够用）。"""
    a, b = divmod(index, 26)
    return f"{_PSEUDO_PREFIX}{_ALPHABET[a % 26]}{_ALPHABET[b]}"


PSEUDO_RE = re.compile(r"\b(" + _PSEUDO_PREFIX + r"[a-z]{2})\b")

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


# ---------------------------------------------------------------------------
# 受控术语（走确定性映射的类别）
# ---------------------------------------------------------------------------
CONTROLLED_TERMS: dict[str, str] = {}
for _group in (glossary.CAMERA_TERMS, glossary.ACTION_TERMS, glossary.NEGATION_TERMS,
               glossary.BODY_TERMS, glossary.SPEECH_TERMS):
    for _k, _v in _group.items():
        if _group is glossary.CAMERA_TERMS:
            _v = glossary.CAMERA_LABEL_TO_NATURAL.get(_v, _v)
        CONTROLLED_TERMS.setdefault(_k, _v)

CONTROLLED_SORTED: list[tuple[str, str]] = sorted(
    CONTROLLED_TERMS.items(), key=lambda kv: (-len(kv[0]), kv[0]))

# ---------------------------------------------------------------------------
# 受保护片段（原样保留，绝不进入 MT 语义）
# ---------------------------------------------------------------------------
PROTECT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<(?:Subject|Picture|Video|Audio)\s+\d+>"),   # 参考标签
    re.compile(r"\((?:S\d+(?:\s*,\s*S\d+)*)\)"),              # 说话人 ID
    re.compile(r"\[Shot\s+\d+\]"),                            # 镜头标签
    re.compile(r"\b\d{2}:\d{2}\.\d{3}\b"),                    # 时间戳
    re.compile(r"\bC\d{2,}\b"),                               # 角色永久 ID
    re.compile(r"\[(?:English|Chinese|Japanese|Korean|French|German|Italian|"
               r"Spanish|Portuguese|Russian|Arabic)\]"),      # 语言标签
    re.compile(r"「[^」]*」"),                                  # 中文引号内容
    re.compile(r"“[^”]*”"),
    re.compile(r"<d>.*?</d>", re.DOTALL),                     # 台词块
    re.compile(r"<(?:scenetrans|cutoff)>"),                   # 连续性标记
]

_ASCII_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


class TranslationUnavailable(RuntimeError):
    """翻译引擎不可用。编译必须显式报错，不得伪造成功。"""


# ---------------------------------------------------------------------------
# MT 幻觉守卫（任务书 §9.3：语义明显错误的翻译不得被当作成功）
#
# 实测证据：Argos 对某些**孤立短片段**会给出流畅但语义完全无关的英文，而且是
# 确定性复现的，例如
#     MT("栏杆边交谈，") == "I'm not sure what I'm talking about."
#     MT("。")         == "I don't know."
#     MT("之")         == "Shit."
# 这类输出比"保留中文"危害大得多：它看起来像正常英文，会被直接写进提示词。
# 因此一旦命中已知幻觉形态，就把该片段判定为**翻译失败**（抛出异常），
# 交给编译器的 `_translate_safe` 保留中文并记录警告——绝不静默采用。
# ---------------------------------------------------------------------------
# 只收录**多词**的、在本项目领域里不可能成立的寒暄/推诿句式。
# 刻意**不**收录单个常见词（here / call / pass / yes / no / ok …）：
# 它们有可能是合法短译（"这里"→"Here."、"打电话"→"Call."），
# 收录会造成误判（fail-closed 也不能以牺牲正确性为代价）。
# 单个汉字的幻觉风险已由上面的"孤立单字守卫 + CHAR_TERMS"从源头消除。
_HALLUCINATION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"i don't know",
        r"i'm sorry",
        r"i'm not sure",
        r"i have no idea",
        r"shall i\b",
        r"what are you talking about",
        r"^\s*(yeah|shit|demon|whatever)\.?\s*$",
    )
]


def looks_hallucinated(text: str) -> bool:
    """判断一段 MT 输出是否是已知的幻觉形态。"""
    t = (text or "").strip()
    if not t:
        return True
    return any(p.search(t) for p in _HALLUCINATION_PATTERNS)


# ---------------------------------------------------------------------------
# MT Provider
# ---------------------------------------------------------------------------
class BaseProvider:
    name = "base"

    def available(self) -> bool:  # pragma: no cover - 接口
        raise NotImplementedError

    def translate(self, text: str) -> str:  # pragma: no cover - 接口
        raise NotImplementedError

    def describe(self) -> dict[str, object]:
        return {"provider": self.name, "available": False}


class NullProvider(BaseProvider):
    """没有可用 MT 时的占位实现：明确失败，而不是静默返回中文。"""

    name = "none"

    def __init__(self, reason: str = "未安装离线翻译引擎") -> None:
        self.reason = reason

    def available(self) -> bool:
        return False

    def translate(self, text: str) -> str:
        raise TranslationUnavailable(self.reason)


class ArgosProvider(BaseProvider):
    """Argos Translate（离线、CPU、本地模型）。"""

    name = "argos"

    def __init__(self, from_code: str = "zh", to_code: str = "en") -> None:
        self.from_code = from_code
        self.to_code = to_code
        self._lock = threading.Lock()
        self._impl = None
        self._error: str | None = None

    def _load(self):
        if self._impl is not None or self._error is not None:
            return self._impl
        try:
            import argostranslate.translate as at  # noqa: PLC0415
            self._impl = at
        except Exception as exc:  # noqa: BLE001
            self._error = f"argostranslate 不可用：{exc}"
        return self._impl

    def available(self) -> bool:
        at = self._load()
        if at is None:
            return False
        try:
            langs = {lang.code for lang in at.get_installed_languages()}
            return self.from_code in langs and self.to_code in langs
        except Exception:  # noqa: BLE001
            return False

    def translate(self, text: str) -> str:
        at = self._load()
        if at is None:
            raise TranslationUnavailable(self._error or "argostranslate 不可用")
        try:
            with self._lock:
                return at.translate(text, self.from_code, self.to_code)
        except Exception as exc:  # noqa: BLE001
            raise TranslationUnavailable(f"Argos 翻译失败：{exc}") from exc

    def describe(self) -> dict[str, object]:
        at = self._load()
        return {
            "provider": self.name,
            "available": self.available(),
            "engine_version": getattr(at, "__version__", "") if at else "",
            "from": self.from_code,
            "to": self.to_code,
            "license": "argostranslate = MIT；zh_en 模型来自 OPUS（许可待逐项核实）",
            "error": self._error,
        }


# ---------------------------------------------------------------------------
# 分词
# ---------------------------------------------------------------------------
@dataclass
class Piece:
    kind: str      # "protected" | "term" | "raw"
    text: str      # 受控/受保护的英文，或中文原样


@dataclass
class Masked:
    pieces: list[Piece] = field(default_factory=list)


def split_pieces(text: str, extra_terms: dict[str, str] | None = None,
                 controlled_only: bool = False) -> list[Piece]:
    """把文本切分为 受保护 / 受控术语 / 原文 三类片段。"""
    extra_sorted = sorted((extra_terms or {}).items(), key=lambda kv: (-len(kv[0]), kv[0]))
    terms = CONTROLLED_SORTED if controlled_only else sorted(
        glossary.TERMS.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    pieces: list[Piece] = []
    i, n = 0, len(text)

    def push(kind: str, value: str) -> None:
        if pieces and pieces[-1].kind == "raw" and kind == "raw":
            pieces[-1].text += value
        else:
            pieces.append(Piece(kind, value))

    while i < n:
        matched = False
        for pat in PROTECT_PATTERNS:
            m = pat.match(text, i)
            if m:
                push("protected", m.group(0))
                i = m.end()
                matched = True
                break
        if matched:
            continue

        for zh, en in extra_sorted:
            if text.startswith(zh, i):
                push("protected", en)
                i += len(zh)
                matched = True
                break
        if matched:
            continue

        hit = None
        for zh, en in terms:
            if text.startswith(zh, i):
                hit = (zh, en)
                break
        if hit:
            push("term", hit[1])
            i += len(hit[0])
            continue

        if _ASCII_WORD.match(text, i):
            m = _ASCII_WORD.match(text, i)
            push("protected", m.group(0))
            i = m.end()
            continue

        push("raw", text[i])
        i += 1
    return _attach_punctuation(pieces)


def _attach_punctuation(pieces: list[Piece]) -> list[Piece]:
    """把"纯标点"片段并入**前一含汉字片段**（让 MT 见到完整句读）。"""
    out = [Piece(p.kind, p.text) for p in pieces]
    for i, piece in enumerate(out):
        if piece.kind == "raw" and piece.text and not has_cjk(piece.text):
            j = i - 1
            while j >= 0 and out[j].kind != "raw":
                j -= 1
            if j >= 0 and has_cjk(out[j].text):
                out[j] = Piece("raw", out[j].text + piece.text)
                out[i] = Piece("raw", "")
    return [p for p in out if p.text]


# ---------------------------------------------------------------------------
# 标点归一（保护 <d> 台词块与引号内容）
# ---------------------------------------------------------------------------
_PUNCT_MAP = {
    "，": ", ", "。": ". ", "、": ", ", "；": "; ", "：": ": ",
    "！": "! ", "？": "? ", "（": " (", "）": ") ", "　": " ",
    "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "·": " ",
}

_PUNCT_SHIELD = re.compile(r"<d>.*?</d>|「[^」]*」|“[^”]*”", re.DOTALL)


def normalize_punctuation(text: str) -> str:
    """把中文标点归一为英文标点，**但完全跳过 <d> 台词块与引号内容**。"""
    if not text:
        return ""
    shielded: list[str] = []

    def stash(m: re.Match[str]) -> str:
        shielded.append(m.group(0))
        return f"\x00{len(shielded) - 1}\x00"

    work = _PUNCT_SHIELD.sub(stash, text)
    for zh, en in _PUNCT_MAP.items():
        work = work.replace(zh, en)
    for idx, original in enumerate(shielded):
        work = work.replace(f"\x00{idx}\x00", original)
    return work


# 衣物/毛发类名词：只有这些词才参与下面的"颜色语序重排"，
# 避免把 "light a candle" 误改成 "a light candle"。
_COLOR_NOUNS = ("coat", "jacket", "suit", "dress", "shirt", "sweater", "uniform",
                "jeans", "skirt", "hat", "scarf", "gloves", "shoes", "boots",
                "hair", "glasses", "tie", "hoodie", "trench")

_COLOR_WORDS = ("dark", "pale", "black", "white", "red", "blue", "green", "yellow",
                "grey", "gray", "brown", "pink", "purple", "orange", "silver",
                "golden", "beige")

# 功能词后缀不接句号的集合（单字映射结果的收尾处理）
_FUNCTION_WORDS = frozenset({
    "from", "at", "to", "toward", "by", "with", "and", "for", "of",
    "also", "both", "still", "very", "more", "most", "takes",
})

# "深色" → "dark" + "大衣" → "a coat" 拼出来是 "dark a coat"；
# 中文的"颜色+名词"在英文里要变成"冠词+颜色+名词"，这里做**确定性**语序重排。
_ARTICLE_REORDER = re.compile(
    r"\b(" + "|".join(_COLOR_WORDS) + r")\s+a\s+(" + "|".join(_COLOR_NOUNS) + r")\b")


def _fix_color_order(text: str) -> str:
    return _ARTICLE_REORDER.sub(lambda m: f"a {m.group(1)} {m.group(2)}", text)


def _clean(text: str) -> str:
    out = normalize_punctuation(text)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([(\[])\s+", r"\1", out)
    out = re.sub(r"\s+([)\]])", r"\1", out)
    out = re.sub(r"\b(then)\s+\1\b", r"\1", out, flags=re.IGNORECASE)
    out = re.sub(r"^[,;:.\s]+", "", out)
    out = _fix_color_order(out)
    return out.strip()


# ---------------------------------------------------------------------------
# 习语归一化（翻译前的**语义等价**改写，不改用户意图）
#
# 证据（_evidence/g3_translation/quality_probe_20261010.txt 同目录的 idiom 探针）：
#   "他一边说话，一边挥手。" 直译 → "he one side says word, side waves"，
#   完全丢失"同时发生"这一语义（属于 §9.3 禁止的明显误译）。
#   中文"一边A，一边B / 一面A，一面B"的确定含义就是"A 与 B 同时发生"，
#   因此归一为"A 同时 B"是**语义等价**改写，不是润色、不是创作。
# ---------------------------------------------------------------------------
_IDIOM_SIMULTANEOUS = re.compile(
    r"(?:一边|一面|一方面)\s*([^，。；,;！？!?\n]+?)\s*[，,]\s*(?:一边|一面|一方面)\s*([^，。；,;！？!?\n]+)")


def normalize_idioms(text: str) -> str:
    """把可确定性解释的中文习语归一为等义写法（只做语义等价替换）。"""
    out = text or ""
    if not out:
        return ""
    prev = None
    while prev != out:            # 连续出现多组时反复归一
        prev = out
        out = _IDIOM_SIMULTANEOUS.sub(lambda m: f"同时，{m.group(1)}，{m.group(2)}", out)
    return out


# ---------------------------------------------------------------------------
# 两条翻译路径
# ---------------------------------------------------------------------------
def _whole_sentence(text: str, provider: BaseProvider,
                    extra_terms: dict[str, str] | None) -> tuple[str, bool]:
    """【非主路径｜仅保留供 A/B 对照复现】整句 + 生造词占位符 → 一次 MT → 还原。

    返回 (英文, 占位符是否全部存活)。
    实测在本机长句上劣化明显，已不作为生产路径；保留它是为了让
    `_evidence/g3_translation/path_ab_20261010.txt` 的结论可随时重跑验证。
    """
    pieces = split_pieces(text, extra_terms, controlled_only=True)
    mapping: dict[str, str] = {}
    buf: list[str] = []
    for piece in pieces:
        if piece.kind == "raw":
            buf.append(piece.text)
        else:
            word = pseudo_word(len(mapping))
            mapping[word] = piece.text
            buf.append(f" {word} ")
    masked = "".join(buf)

    if not has_cjk(masked):
        for w, v in mapping.items():
            masked = masked.replace(w, v)
        return _clean(masked), True

    out = provider.translate(masked)
    for word in mapping:
        if not re.search(r"\b" + re.escape(word) + r"\b", out or ""):
            return "", False
    for word, value in mapping.items():
        out = re.sub(r"\b" + re.escape(word) + r"\b", value, out)
    return _clean(out), True


def _cjk_core(text: str) -> str:
    """只保留汉字（去掉标点等），用于判断"是不是孤立单字"。"""
    return "".join(ch for ch in text if _CJK_RE.match(ch))


def _fragment(text: str, provider: BaseProvider,
              extra_terms: dict[str, str] | None) -> str:
    """回退路径 = 主路径：只把**含汉字且长度 ≥2** 的片段送 MT，其余片段确定性处理。

    两条硬规则（均有实测证据，见 _evidence/g3_translation/quality_probe_20261010.txt）：
      1. 绝不把**无汉字**片段送进 MT（纯标点会得到 "I don't know."）。
      2. 绝不把**孤立单字**送进 MT（`的`→"Yes."、`之`→"Shit."、`到`→"Present." 全是幻觉）；
         单字一律查 `glossary.CHAR_TERMS`，未收录则丢弃并计数（丢弃量对外可见）。

    注意：标点会被 `_attach_punctuation` 并入前一片段，因此判定单字必须**先剥离标点**，
    否则 "的，" 会因为长度变成 2 而漏过守卫并译出 "it's"（本机实测到的缺陷）。
    """
    pieces = split_pieces(text, extra_terms, controlled_only=False)
    parts: list[tuple[str, bool]] = []
    for piece in pieces:
        if piece.kind != "raw":
            parts.append((piece.text, True))
            continue
        chunk = piece.text
        if not has_cjk(chunk):
            parts.append((chunk, False))
            continue
        core = _cjk_core(chunk)
        if len(core) == 1:
            mapped = glossary.CHAR_TERMS.get(core)
            if mapped is None:
                _stats["dropped_chars"] = _stats.get("dropped_chars", 0) + 1
                continue
            tail = normalize_punctuation(
                "".join(ch for ch in chunk if not _CJK_RE.match(ch)))
            # 功能词后面的句号是中文断句残留（"从。"→"from."），英文里不该出现
            if mapped in _FUNCTION_WORDS:
                tail = tail.replace(".", "")
            parts.append((mapped + tail, True))
            continue
        out = provider.translate(chunk).strip()
        if looks_hallucinated(out):
            _stats["hallucinations"] = _stats.get("hallucinations", 0) + 1
            raise TranslationUnavailable(
                f"离线翻译引擎对片段「{chunk.strip()}」给出了无效输出（{out}），"
                "已拒绝采用，该字段保留中文原文。")
        parts.append((out, False))

    # 句中首字母小写（MT 会把每个片段当独立句子而给出大写开头）
    normalized: list[str] = []
    for i, (chunk, protected) in enumerate(parts):
        chunk = chunk.strip()
        if not chunk:
            continue
        if i > 0 and not protected and chunk[:1].isupper():
            # 不误伤全大写缩略语与 <Label N> 形式
            if not chunk.isupper() and not chunk.startswith("<"):
                chunk = chunk[0].lower() + chunk[1:]
        # 非末尾片段去掉句末句号：MT 对每个片段都补了句号，
        # 拼起来会变成 "twenty years old. a young woman." 这种假断句。
        if not protected and i < len(parts) - 1:
            chunk = chunk.rstrip(". ")
        if chunk:
            normalized.append(chunk)
    return _clean(" ".join(normalized))


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------
_default_provider: BaseProvider | None = None
_cache: dict[str, str] = {}
_cache_lock = threading.Lock()
_stats: dict[str, int] = {"fragment": 0, "dropped_chars": 0}


def get_provider() -> BaseProvider:
    global _default_provider
    if _default_provider is None:
        argos = ArgosProvider()
        _default_provider = argos if argos.available() else NullProvider(
            str(argos.describe().get("error") or "未找到已安装的中→英离线模型")
        )
    return _default_provider


def set_provider(provider: BaseProvider | None) -> None:
    """测试注入用。"""
    global _default_provider
    _default_provider = provider


def provider_status() -> dict[str, object]:
    status = dict(get_provider().describe())
    status["stats"] = dict(_stats)
    return status


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
        for k in _stats:
            _stats[k] = 0


def translate_zh_to_en(text: str, provider: BaseProvider | None = None,
                       protect_terms: dict[str, str] | None = None) -> str:
    """把一段中文翻译为英文（受控术语保护 + 整句离线 MT，失败自动回退分片）。

    `protect_terms`：需要原样保留的词条（例如角色姓名、专有名词）。

    MT 不可用时抛 `TranslationUnavailable` —— 由调用方决定"保留中文并报错"，
    绝不在本函数内静默降级成假成功。
    """
    src = normalize_idioms((text or "").strip())
    if not src:
        return ""

    prov = provider or get_provider()
    key = f"{prov.name}|{src}|{sorted((protect_terms or {}).items())}"
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached

    need_mt = any(p.kind == "raw" and has_cjk(p.text)
                  for p in split_pieces(src, protect_terms, controlled_only=False))

    if not need_mt:
        pieces = split_pieces(src, protect_terms, controlled_only=False)
        out = _clean(" ".join(p.text for p in pieces))
        with _cache_lock:
            _cache[key] = out
        return out

    if not prov.available():
        raise TranslationUnavailable(
            str(prov.describe().get("error") or "离线翻译引擎不可用"))

    # 主路径 = 分片（术语确定性映射 + 仅汉字片段送 MT）。
    # 理由：本机实验证明 Argos 对句中插入任何标记都会不可预测地劣化
    # （见 _evidence/g3_translation/pseudoword_experiment.txt），
    # 而分片路径对"官方镜头词汇 / 方位 / 否定 / 动作"可逐项断言，稳定可验证。
    out = _fragment(src, prov, protect_terms)
    with _cache_lock:
        _stats["fragment"] += 1
        _cache[key] = out
    return out
