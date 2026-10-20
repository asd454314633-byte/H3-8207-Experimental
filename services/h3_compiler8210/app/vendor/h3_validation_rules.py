from __future__ import annotations

import re
from typing import Literal, Sequence, TypeAlias

H3Mode: TypeAlias = Literal["T2VA", "I2VA", "FL2VA", "L2VA", "R2VA"]
Severity: TypeAlias = Literal["error", "warning"]
RuleMessage: TypeAlias = tuple[Severity, str, str]

BASE_SECTIONS = (
    "integrated_multimodal_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
REF_SECTIONS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
I2VA_ALIGNMENT = (
    "For the target video, at 0.00 seconds into the target video, <Picture 1> "
    "(from [Shot 1]) is fully referenced."
)
FL2VA_ALIGNMENT = (
    "How the reference pictures align with the target video — Picture 1 (from Shot 1) "
    "aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {final_shot}) "
    "aligns with the {duration:.2f}-second mark of the target video."
)
L2VA_ALIGNMENT = (
    "How the reference pictures align with the target video — <Picture 1> (from [Shot {final_shot}]) "
    "aligns with the {duration:.2f}-second mark of the target video."
)
SHOT_PATTERN = re.compile(r"\[Shot\s+(\d+)\]")
TIMESTAMP_PATTERN = re.compile(r"\bAt\s+(\d{2}):(\d{2})\.(\d{3})\b")
REFERENCE_PATTERN = re.compile(r"<(Subject|Picture|Video|Audio)\s+(\d+)>")
DEFINITION_LINE_PATTERN = re.compile(r"^<(Subject|Picture|Video|Audio)\s+(\d+)>", re.MULTILINE)
DIALOGUE_PATTERN = re.compile(r"<d>\[[A-Za-z][A-Za-z -]*\]\s+.+?</d>", re.DOTALL)
SPEAKER_PATTERN = re.compile(r"\((S\d+(?:\s*,\s*S\d+)*)\)")
LOCAL_SPEAKER_BOUNDARY_PATTERN = re.compile(r"(?:\r?\n\s*\r?\n|(?<=[.!?])\s+)")
HEADER_PATTERN = re.compile(
    r"^(integrated_multimodal_description:|subject_definitions:|summary:|retention_analysis:|"
    r"detailed_description:|overall_soundscape:|non_diegetic_music:)[^\r\n]*$",
    re.MULTILINE,
)
RETENTION_LINE_PATTERN = re.compile(
    r"^<(Subject|Picture|Video|Audio)\s+(\d+)>[^:\r\n]*:\s*([a-z_]+)\b[^\r\n]*$",
    re.MULTILINE,
)
VISUAL_RETENTION_MARKERS = frozenset(
    {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"}
)
AUDIO_RETENTION_MARKERS = frozenset(
    {"fully_copy", "partially_copy", "reference", "weak_reference"}
)
RETENTION_MARKERS = VISUAL_RETENTION_MARKERS | AUDIO_RETENTION_MARKERS


def _error(messages: list[RuleMessage], code: str, message: str) -> None:
    messages.append(("error", code, message))


def detect_mode(prompt: str) -> H3Mode | None:
    headers = list(HEADER_PATTERN.finditer(prompt))
    schema_headers = tuple(
        match for match in headers if match.group(1) in ("integrated_multimodal_description:", *REF_SECTIONS[:4])
    )
    if not schema_headers:
        return None
    if schema_headers[0].group(1) in REF_SECTIONS[:4]:
        return "R2VA"
    if prompt.startswith(I2VA_ALIGNMENT):
        return "I2VA"
    if prompt.startswith("How the reference pictures align"):
        return "L2VA" if "<Picture 1>" in prompt.partition("\n")[0] else "FL2VA"
    return "T2VA"


def section_body(prompt: str, header: str, following: Sequence[str] = ()) -> str:
    del following
    matches = list(HEADER_PATTERN.finditer(prompt))
    matching = [match for match in matches if match.group(1) == header]
    if not matching:
        return ""
    selected = matching[0]
    next_headers = [match.start() for match in matches if match.start() > selected.start()]
    ending = min(next_headers, default=len(prompt))
    return prompt[selected.start() + len(header):ending]


def validate_timeline(timeline: str, duration: int) -> tuple[tuple[int, ...], list[RuleMessage]]:
    messages: list[RuleMessage] = []
    shots = list(SHOT_PATTERN.finditer(timeline))
    shot_numbers = [int(match.group(1)) for match in shots]
    if shot_numbers and shot_numbers != list(range(1, len(shot_numbers) + 1)):
        _error(messages, "shot_sequence", "shot numbers must be sequential from 1")
    timestamps: list[float] = []
    for index, shot in enumerate(shots):
        end = shots[index + 1].start() if index + 1 < len(shots) else len(timeline)
        timestamp = TIMESTAMP_PATTERN.match(timeline[shot.end():end].lstrip())
        if index == 0 and timestamp is not None:
            _error(messages, "timestamp_first_shot", "Shot 1 must not have a timestamp")
        if index > 0 and timestamp is None:
            _error(messages, "timestamp_missing", "later shots must begin with a timestamp")
        if timestamp is not None:
            minute, second, millisecond = (int(value) for value in timestamp.groups())
            timestamps.append(minute * 60 + second + millisecond / 1000)
    if any(timestamp >= duration for timestamp in timestamps):
        _error(messages, "timestamp_range", "timestamps must be inside the duration")
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        _error(messages, "timestamp_order", "timestamps must strictly increase")
    return tuple(shot_numbers), messages


def validate_references(prompt: str) -> list[RuleMessage]:
    messages: list[RuleMessage] = []
    definitions = section_body(prompt, "subject_definitions:")
    definition_labels = DEFINITION_LINE_PATTERN.findall(definitions)
    available = set(definition_labels)
    mentioned_in_definitions = set(REFERENCE_PATTERN.findall(definitions))
    if len(definition_labels) != len(set(definition_labels)):
        _error(messages, "duplicate_definition", "reference labels must be defined only once")
    used_sections = "".join(
        section_body(prompt, header)
        for header in ("summary:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:")
    )
    used = set(REFERENCE_PATTERN.findall(used_sections))
    retention = section_body(prompt, "retention_analysis:")
    analyzed = set(REFERENCE_PATTERN.findall(retention))
    source_only = {
        label for label in mentioned_in_definitions - available - used - analyzed
        if label[0] in {"Picture", "Video"}
    }
    required = (mentioned_in_definitions | used | analyzed) - source_only
    if required.difference(available):
        _error(messages, "undefined_reference", "reference label is not defined")
    for label in set(definition_labels).difference(used):
        messages.append(("warning", "unused_reference", f"unused reference label: <{label[0]} {label[1]}>"))
    entries = [((match.group(1), match.group(2)), match.group(3)) for match in RETENTION_LINE_PATTERN.finditer(retention)]
    retained_labels = [label for label, _marker in entries]
    if len(retained_labels) != len(set(retained_labels)):
        _error(messages, "duplicate_retention", "reference labels need one retention line")
    if set(retained_labels) != required:
        _error(messages, "retention_coverage", "retention lines must cover every tracked reference label; source-only pictures and videos are exempt")
    for (kind, _number), marker in entries:
        if marker not in RETENTION_MARKERS:
            _error(messages, "retention_marker", "retention marker is not recognized")
        elif kind == "Audio" and marker not in AUDIO_RETENTION_MARKERS:
            _error(messages, "retention_marker_family", "audio reference uses a visual retention marker")
        elif kind != "Audio" and marker not in VISUAL_RETENTION_MARKERS:
            _error(messages, "retention_marker_family", "visual reference uses an audio retention marker")
    return messages


def validate_speakers(prompt: str) -> list[RuleMessage]:
    messages: list[RuleMessage] = []
    speaker_blocks: list[str] = []
    previous_end = 0
    for dialogue in DIALOGUE_PATTERN.finditer(prompt):
        preceding_text = prompt[previous_end:dialogue.start()]
        local_context = LOCAL_SPEAKER_BOUNDARY_PATTERN.split(preceding_text)[-1]
        local_bindings = SPEAKER_PATTERN.findall(local_context)
        if not local_bindings:
            _error(messages, "speaker_missing", "each dialogue block requires a local speaker ID")
        else:
            speaker_blocks.append(local_bindings[-1])
        previous_end = dialogue.end()
    known: set[int] = set()
    next_id = 1
    for block in speaker_blocks:
        for speaker in block.replace(" ", "").split(","):
            number = int(speaker[1:])
            if number not in known:
                if number != next_id:
                    _error(messages, "speaker_sequence", "speaker IDs must follow vocal-event order")
                    return messages
                known.add(number)
                next_id += 1
    return messages


def required_alignment(mode: H3Mode | None, duration: int, final_shot: int) -> str | None:
    if mode == "I2VA":
        return I2VA_ALIGNMENT
    if mode == "FL2VA":
        return FL2VA_ALIGNMENT.format(final_shot=final_shot, duration=duration)
    if mode == "L2VA":
        return L2VA_ALIGNMENT.format(final_shot=final_shot, duration=duration)
    return None
