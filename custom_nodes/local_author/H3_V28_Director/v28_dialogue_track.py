# -*- coding: utf-8 -*-
"""Deterministic, lossless dialogue segmentation for V28.2.

The LLM never owns source-dialogue copying.  This module assigns contiguous
source spans to time-budgeted segments and rejects any loss, duplication or
reordering before a production plan can consume the track.
"""
from __future__ import annotations

from collections import Counter
import re
import unicodedata


_SENTENCE = re.compile(r".*?(?:[。！？!?；;]+|$)", re.S)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", str(text))


def _sentence_units(source: str) -> list[str]:
    units = [match.group(0) for match in _SENTENCE.finditer(source) if match.group(0)]
    return units or ([source] if source else [])


def validate_dialogue_track(source: str, segment_dialogues: list[str]) -> dict:
    expected = normalize(source)
    actual = normalize("".join(segment_dialogues))
    expected_counts, actual_counts = Counter(expected), Counter(actual)
    missing = sum((expected_counts - actual_counts).values())
    duplicated = sum((actual_counts - expected_counts).values())
    reordered = int(actual != expected and missing == 0 and duplicated == 0)
    return {
        "passed": actual == expected,
        "MISSING_CHAR": missing,
        "DUPLICATED_CHAR": duplicated,
        "REORDERED_TEXT": reordered,
        "normalized_source": expected,
        "normalized_concat": actual,
    }


def split_dialogue(source: str, durations_s: list[float]) -> dict:
    """Split source into contiguous, lossless spans weighted by duration.

    Sentence-ending punctuation is preferred.  When there are fewer sentences
    than requested segments, deterministic character boundaries are used; no
    character is generated, removed, normalized away or reordered.
    """
    source = str(source)
    durations = [float(x) for x in durations_s]
    if not source:
        raise ValueError("SOURCE_DIALOGUE must not be empty")
    if not durations or any(x <= 0 for x in durations):
        raise ValueError("durations_s must contain positive values")
    count = len(durations)
    units = _sentence_units(source)
    if len(units) < count:
        units = list(source)

    total_weight = sum(durations)
    total_chars = len(source)
    cumulative_targets = []
    running = 0.0
    for duration in durations[:-1]:
        running += duration
        cumulative_targets.append(total_chars * running / total_weight)

    unit_ends = []
    position = 0
    for unit in units:
        position += len(unit)
        unit_ends.append(position)

    boundaries = []
    min_index = 0
    for i, target in enumerate(cumulative_targets):
        remaining_boundaries = len(cumulative_targets) - i - 1
        max_index = len(unit_ends) - remaining_boundaries - 2
        if max_index < min_index:
            raise ValueError("dialogue cannot be divided into requested segments")
        chosen = min(range(min_index, max_index + 1),
                     key=lambda idx: (abs(unit_ends[idx] - target), idx))
        boundaries.append(unit_ends[chosen])
        min_index = chosen + 1

    spans = []
    start = 0
    for segment_id, (end, duration) in enumerate(
            zip(boundaries + [len(source)], durations), start=1):
        spans.append({"id": segment_id, "duration_s": duration,
                      "dialogue": source[start:end]})
        start = end

    receipt = validate_dialogue_track(source, [s["dialogue"] for s in spans])
    if not receipt["passed"]:
        raise RuntimeError(f"deterministic dialogue integrity failure: {receipt}")
    return {"SOURCE_DIALOGUE": source, "segments": spans, "integrity": receipt,
            "owner": "DETERMINISTIC_DIALOGUE_TRACK"}
