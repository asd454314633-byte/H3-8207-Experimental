from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence

from .h3_validation_rules import (  # noqa: E402
    BASE_SECTIONS,
    DIALOGUE_PATTERN,
    FL2VA_ALIGNMENT,
    HEADER_PATTERN,
    H3Mode,
    I2VA_ALIGNMENT,
    L2VA_ALIGNMENT,
    REF_SECTIONS,
    Severity,
    detect_mode,
    required_alignment,
    section_body,
    validate_references,
    validate_speakers,
    validate_timeline,
)

MAX_PROMPT_CHARS = 7000
MIN_DURATION = 4
MAX_DURATION = 15


@dataclass(frozen=True, slots=True)
class ValidationMessage:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MediaManifest:
    first_frames: int = 0
    last_frames: int = 0
    reference_images: int = 0
    reference_videos: int = 0
    reference_audios: int = 0

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> MediaManifest:
        field_names = (
            "first_frames",
            "last_frames",
            "reference_images",
            "reference_videos",
            "reference_audios",
        )
        unknown = set(value).difference(field_names)
        if unknown:
            raise ValueError(f"unknown manifest fields: {sorted(unknown)}")
        normalized: dict[str, int] = {}
        for field_name in field_names:
            raw = value.get(field_name, 0)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
            normalized[field_name] = raw
        return cls(**normalized)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    mode: H3Mode | None
    char_count: int
    messages: tuple[ValidationMessage, ...]

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.messages)


def _append_error(messages: list[ValidationMessage], code: str, message: str) -> None:
    messages.append(ValidationMessage("error", code, message))


def _validate_manifest(mode: H3Mode | None, manifest: MediaManifest, messages: list[ValidationMessage]) -> None:
    has_keyframe = manifest.first_frames > 0 or manifest.last_frames > 0
    has_reference = any(
        (manifest.reference_images, manifest.reference_videos, manifest.reference_audios)
    )
    if has_keyframe and has_reference:
        _append_error(messages, "media_role_conflict", "keyframes cannot be mixed with references")
    if manifest.reference_audios > 0 and not (
        manifest.reference_images > 0 or manifest.reference_videos > 0
    ):
        _append_error(messages, "audio_only_reference", "reference audio needs an image or video")
    counts = (
        manifest.first_frames,
        manifest.last_frames,
        manifest.reference_images,
        manifest.reference_videos,
        manifest.reference_audios,
    )
    valid_for_mode = {
        "T2VA": counts == (0, 0, 0, 0, 0),
        "I2VA": counts == (1, 0, 0, 0, 0),
        "FL2VA": counts == (1, 1, 0, 0, 0),
        "L2VA": counts == (0, 1, 0, 0, 0),
        "R2VA": counts[0] == 0 and counts[1] == 0 and (counts[2] > 0 or counts[3] > 0),
    }
    if mode is not None and not valid_for_mode[mode]:
        _append_error(messages, "mode_media_requirement", "media roles do not match the selected mode")


def validate_prompt(
    prompt: str,
    duration: int,
    expected_mode: H3Mode | None = None,
    manifest: MediaManifest | None = None,
) -> ValidationReport:
    detected_mode = detect_mode(prompt)
    schema_mode = detected_mode or expected_mode
    selected_mode = expected_mode or detected_mode
    messages: list[ValidationMessage] = []
    if detected_mode is None:
        _append_error(messages, "unrecognized_mode", "prompt does not match an H3 mode")
    if expected_mode is not None and detected_mode is not None and expected_mode != detected_mode:
        _append_error(messages, "mode_mismatch", "declared mode does not match the detected prompt schema")
    if isinstance(duration, bool) or not isinstance(duration, int) or not MIN_DURATION <= duration <= MAX_DURATION:
        _append_error(messages, "duration_range", "duration must be 4 through 15 seconds")
    if len(prompt) > MAX_PROMPT_CHARS:
        _append_error(messages, "prompt_too_long", "prompt exceeds 7000 characters")
    sections = REF_SECTIONS if schema_mode == "R2VA" else BASE_SECTIONS
    header_matches = list(HEADER_PATTERN.finditer(prompt))
    occurrences = {
        section: [match for match in header_matches if match.group(1) == section]
        for section in sections
    }
    if any(not matches for matches in occurrences.values()):
        _append_error(messages, "missing_section", "prompt is missing a required section")
    if any(len(matches) > 1 for matches in occurrences.values()):
        _append_error(messages, "duplicate_section", "required section headers must occur exactly once")
    indices = [matches[0].start() for matches in occurrences.values() if matches]
    if len(indices) == len(sections) and indices != sorted(indices):
        _append_error(messages, "section_order", "prompt sections are out of order")
    if schema_mode == "R2VA" and any(match.group(1) == BASE_SECTIONS[0] for match in header_matches):
        _append_error(messages, "mixed_schema", "Ref2VA cannot contain base-mode sections")
    if schema_mode != "R2VA" and any(match.group(1) in REF_SECTIONS[:4] for match in header_matches):
        _append_error(messages, "mixed_schema", "base modes cannot contain Ref2VA sections")
    for section, matches in occurrences.items():
        if len(matches) == 1 and not section_body(prompt, section).strip():
            _append_error(messages, "empty_section", f"required section has an empty body: {section}")
    timeline_header = "detailed_description:" if schema_mode == "R2VA" else BASE_SECTIONS[0]
    timeline_end = ("overall_soundscape:",)
    timeline = section_body(prompt, timeline_header, timeline_end)
    shot_numbers, timeline_messages = validate_timeline(timeline, duration)
    if timeline.strip() and (
        not shot_numbers or shot_numbers[0] != 1
        or (schema_mode != "R2VA" and not timeline.strip().startswith("[Shot 1]"))
    ):
        _append_error(messages, "timeline_start", "timeline must start at [Shot 1]; only Ref2VA allows preceding style prose")
    messages.extend(ValidationMessage(*message) for message in timeline_messages)
    alignment = required_alignment(selected_mode, duration, shot_numbers[-1] if shot_numbers else 1)
    if alignment is not None and not prompt.startswith(alignment + "\n\n"):
        _append_error(messages, "alignment_instruction", "prompt requires the exact alignment instruction")
    first_section = occurrences[sections[0]][0] if occurrences[sections[0]] else None
    expected_prefix = (alignment + "\n\n") if alignment is not None else ""
    if first_section is not None and prompt[:first_section.start()] != expected_prefix:
        _append_error(messages, "starting_header", "prompt must start with its required schema header")
    if schema_mode == "R2VA":
        messages.extend(ValidationMessage(*message) for message in validate_references(prompt))
    if "<d>" in DIALOGUE_PATTERN.sub("", prompt) or "</d>" in DIALOGUE_PATTERN.sub("", prompt):
        _append_error(messages, "dialogue_tag", "dialogue tags must have a language and closing tag")
    messages.extend(ValidationMessage(*message) for message in validate_speakers(prompt))
    if "camera moves" in timeline.lower():
        messages.append(
            ValidationMessage("warning", "camera_ambiguity", "camera motion lacks a motion type")
        )
    soundscape = section_body(prompt, "overall_soundscape:", ("non_diegetic_music:",)).strip()
    music = section_body(prompt, "non_diegetic_music:").strip()
    if music and music.lower() != "n/a" and soundscape.casefold() == music.casefold():
        messages.append(ValidationMessage("warning", "audio_ambiguity", "audio wording is duplicated"))
    if manifest is not None:
        _validate_manifest(selected_mode, manifest, messages)
    return ValidationReport(mode=detected_mode, char_count=len(prompt), messages=tuple(messages))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a MiniMax H3 prompt")
    parser.add_argument("prompt_path", metavar="PROMPT_PATH")
    parser.add_argument("--duration", required=True, type=int)
    parser.add_argument("--mode", choices=("T2VA", "I2VA", "FL2VA", "L2VA", "R2VA"))
    parser.add_argument("--manifest", metavar="MANIFEST.json")
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        prompt = sys.stdin.read() if arguments.prompt_path == "-" else Path(arguments.prompt_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    try:
        manifest = _load_manifest(arguments.manifest) if arguments.manifest else None
    except (OSError, ValueError) as error:
        print(f"manifest error: {error}", file=sys.stderr)
        return 2
    report = validate_prompt(prompt, arguments.duration, arguments.mode, manifest)
    print(f"valid={report.valid} mode={report.mode or 'unknown'} chars={report.char_count}/{MAX_PROMPT_CHARS}")
    for message in report.messages:
        print(f"{message.severity} {message.code}: {message.message}")
    return 0 if report.valid else 1


def _load_manifest(path: str) -> MediaManifest:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must contain a JSON object")
    return MediaManifest.from_mapping(value)


if __name__ == "__main__":
    raise SystemExit(main())
