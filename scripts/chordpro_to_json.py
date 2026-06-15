#!/usr/bin/env python3
"""Generate a prochords.py JSON spec by matching ChordPro lyrics to .pro slides."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prochords import iter_text_elements, load, rtf_to_plain


CHORD_RE = re.compile(r"\[([^\]]+)\]")
DIRECTIVE_RE = re.compile(r"^\s*\{[^}]+}\s*$")
TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
QUOTE_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


@dataclass
class Token:
    text: str
    original_start: int
    original_end: int
    original_indices: list[int]


@dataclass
class ChordEvent:
    chord: str
    position: int
    token_index: int | None = None
    token_offset: int = 0


@dataclass
class Progression:
    section: str
    lines: list[list[str]]


@dataclass
class SlideRecord:
    index: int
    cue_uuid: str
    plain: str
    text: object


def normalize_characters(text: str) -> tuple[str, list[int]]:
    normalized = []
    original_indices = []
    index = 0
    while index < len(text):
        if text[index : index + 3] == " - ":
            index += 3
            continue
        char = text[index].translate(QUOTE_MAP)
        normalized.append(char)
        original_indices.append(index)
        index += 1
    return "".join(normalized), original_indices


def tokenize(text: str) -> list[Token]:
    normalized, index_map = normalize_characters(text)
    tokens = []
    for match in TOKEN_RE.finditer(normalized):
        indices = index_map[match.start() : match.end()]
        tokens.append(
            Token(
                text=match.group(0).lower(),
                original_start=indices[0],
                original_end=indices[-1] + 1,
                original_indices=indices,
            )
        )
    return tokens


def edit_distance_one_or_less(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1 or min(len(left), len(right)) < 5:
        return False
    first = second = differences = 0
    while first < len(left) and second < len(right):
        if left[first] == right[second]:
            first += 1
            second += 1
            continue
        differences += 1
        if differences > 1:
            return False
        if len(left) == len(right):
            first += 1
            second += 1
        elif len(left) > len(right):
            first += 1
        else:
            second += 1
    return True


def tokens_match(slide_token: str, chart_token: str) -> bool:
    return slide_token == chart_token or edit_distance_one_or_less(slide_token, chart_token)


def clean_chord(chord: str) -> str | None:
    cleaned = chord.strip()
    while cleaned.startswith("(") and cleaned.endswith(")") and len(cleaned) > 2:
        cleaned = cleaned[1:-1].strip()
    if not re.match(r"^[A-G](?:#|b)?[A-Za-z0-9#b+()^./-]*$", cleaned):
        return None
    return cleaned


def real_chords_in_line(line: str) -> list[str]:
    chords = []
    for match in CHORD_RE.finditer(line):
        chord = clean_chord(match.group(1))
        if chord:
            chords.append(chord)
    return chords


def is_progression_only_line(line: str) -> bool:
    if not real_chords_in_line(line):
        return False
    visible = CHORD_RE.sub("", line)
    visible = re.sub(r"\([^)]*\)", "", visible)
    visible = re.sub(r"[|:\s]+", "", visible)
    return not visible


def remove_performance_notes(text: str) -> str:
    return re.sub(r"\((?:to\b|last\b|repeat\b|tag\b|ch\b)[^)]*\)", "", text, flags=re.IGNORECASE)


def parse_chordpro(path: Path) -> tuple[str, list[Token], list[ChordEvent], list[Progression]]:
    full_text_parts = []
    events = []
    progressions: list[Progression] = []
    current_section = ""
    current_progression: Progression | None = None
    current_position = 0

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        directive_match = re.match(r"^\s*\{\s*comment\s*:\s*([^}]+)}\s*$", raw_line, re.IGNORECASE)
        if directive_match:
            current_section = directive_match.group(1).strip()
            current_progression = None
            continue
        if not raw_line.strip() or DIRECTIVE_RE.match(raw_line):
            current_progression = None
            continue

        real_line_chords = real_chords_in_line(raw_line)
        if is_progression_only_line(raw_line):
            if current_progression is None:
                current_progression = Progression(current_section, [])
                progressions.append(current_progression)
            current_progression.lines.append(real_line_chords)
            continue
        else:
            current_progression = None

        if raw_line.startswith("CCLI Song #") or raw_line.startswith("© ") or raw_line.startswith("For use solely"):
            break

        line_parts = []
        line_position = 0
        cursor = 0
        for match in CHORD_RE.finditer(raw_line):
            visible = raw_line[cursor : match.start()]
            line_parts.append(visible)
            line_position += len(visible)
            chord = clean_chord(match.group(1))
            if chord:
                events.append(ChordEvent(chord, current_position + line_position))
            cursor = match.end()

        tail = raw_line[cursor:]
        line_parts.append(tail)
        plain_line = remove_performance_notes("".join(line_parts))
        full_text_parts.append(plain_line)
        current_position += len(plain_line) + 1

    full_text = "\n".join(full_text_parts) + "\n"
    tokens = tokenize(full_text)
    attach_events_to_tokens(events, tokens, full_text)
    return full_text, tokens, events, progressions


def chordpro_key(path: Path) -> str | None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*\{\s*key\s*:\s*([^}]+)}\s*$", raw_line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def attach_events_to_tokens(events: list[ChordEvent], tokens: list[Token], full_text: str) -> None:
    for event in events:
        for index, token in enumerate(tokens):
            if token.original_start <= event.position < token.original_end:
                event.token_index = index
                event.token_offset = sum(1 for original_index in token.original_indices if original_index < event.position)
                break
            if event.position < token.original_start:
                if "\n" in full_text[event.position : token.original_start]:
                    break
                event.token_index = index
                event.token_offset = 0
                break


def find_match(slide_tokens: list[Token], chart_tokens: list[Token]) -> int | None:
    return find_match_from(slide_tokens, chart_tokens, 0)


def find_match_from(slide_tokens: list[Token], chart_tokens: list[Token], start_index: int) -> int | None:
    if not slide_tokens:
        return None
    width = len(slide_tokens)
    for start in range(start_index, len(chart_tokens) - width + 1):
        if all(tokens_match(slide_tokens[offset].text, chart_tokens[start + offset].text) for offset in range(width)):
            return start
    return None


def offset_in_token(token: Token, offset: int) -> int:
    if offset <= 0:
        return token.original_start
    if offset >= len(token.original_indices):
        return token.original_end
    return token.original_indices[offset]


def build_ranges(plain: str, raw_chords: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for chord in sorted(raw_chords, key=lambda item: (item["start"], item["chord"])):
        key = (chord["start"], chord["chord"])
        if key in seen:
            continue
        if unique and chord["chord"] == unique[-1]["chord"]:
            previous_start = unique[-1]["start"]
            if "\n" in plain[previous_start : chord["start"] + 1]:
                continue
        seen.add(key)
        unique.append(chord)

    ranges = []
    for index, chord in enumerate(unique):
        start = chord["start"]
        end = unique[index + 1]["start"] if index + 1 < len(unique) else len(plain)
        newline = plain.find("\n", start, end)
        if newline != -1:
            end = newline
        while end > start and plain[end - 1].isspace():
            end -= 1
        if end <= start:
            end = min(len(plain), start + 1)
        if end > start:
            ranges.append({"start": start, "end": end, "chord": chord["chord"]})
    return ranges


def normalized_title(text: str) -> str:
    return " ".join(token.text for token in tokenize(text))


def slide_records(pres) -> list[SlideRecord]:
    records = []
    slide_index = -1
    for cue in pres.cues:
        for action in cue.actions:
            if not action.HasField("slide"):
                continue
            slide_index += 1
            base_slide = action.slide.presentation.base_slide
            for slide_element in base_slide.elements:
                element = slide_element.element
                if element.HasField("text"):
                    records.append(
                        SlideRecord(
                            index=slide_index,
                            cue_uuid=cue.uuid.string,
                            plain=rtf_to_plain(bytes(element.text.rtf_data)).rstrip("\n"),
                            text=element.text,
                        )
                    )
                    break
            break
    return records


def ordered_slide_records(pres, records: list[SlideRecord]) -> list[SlideRecord]:
    record_by_cue_uuid = {record.cue_uuid: record for record in records}
    ordered = []
    seen = set()
    for cue_group in pres.cue_groups:
        for cue_uuid in cue_group.cue_identifiers:
            record = record_by_cue_uuid.get(cue_uuid.string)
            if record and record.index not in seen:
                ordered.append(record)
                seen.add(record.index)
    for record in records:
        if record.index not in seen:
            ordered.append(record)
    return ordered


def group_targets(pres, records: list[SlideRecord], group_name_part: str, title: str) -> list[SlideRecord]:
    record_by_cue_uuid = {record.cue_uuid: record for record in records}
    targets = []
    section_names = {"intro", "ending", "outro", "instrumental", "turnaround"}
    for cue_group in pres.cue_groups:
        if group_name_part not in cue_group.group.name.lower():
            continue
        for cue_uuid in cue_group.cue_identifiers:
            record = record_by_cue_uuid.get(cue_uuid.string)
            if not record:
                continue
            normalized = normalized_title(record.plain)
            if not normalized or normalized == title or normalized in section_names:
                targets.append(record)
                break
    return targets


def placeholder_line(chords: list[str]) -> str:
    return "\u2001".join("\u200b" for _ in chords)


def progression_entry(lines: list[list[str]], base_plain: str) -> dict:
    flattened = [chord for line in lines for chord in line]
    text_lines = [placeholder_line(flattened)] if flattened else []
    chords = []
    offset = 0
    for line_index, line in enumerate([flattened] if flattened else []):
        for chord_index, chord in enumerate(line):
            start = offset + chord_index * 2
            chords.append({"start": start, "end": start + 1, "chord": chord})
        offset += len(text_lines[line_index]) + 1
    placeholder_text = "\n".join(text_lines)
    if base_plain == "":
        return {"text": placeholder_text, "chords": chords}
    return {"prepend_text": placeholder_text + "\n", "chords": chords}


def chunked_progression(chords: list[str], width: int = 4) -> list[list[str]]:
    return [chords[index : index + width] for index in range(0, len(chords), width) if chords[index : index + width]]


def choose_progression(progressions: list[Progression], preferred_names: tuple[str, ...], fallback: str) -> Progression | None:
    for progression in progressions:
        section = progression.section.lower()
        if any(name in section for name in preferred_names):
            return progression
    if not progressions:
        return None
    return progressions[0] if fallback == "first" else progressions[-1]


def song_progression_override(song_name: str, group_name: str) -> list[list[str]] | None:
    song = song_name.lower()
    group = group_name.lower()
    if song == "king of kings" and "intro" in group:
        return [["C"]]
    if song == "how he loves" and ("intro" in group or "ending" in group or "outro" in group):
        return [["A", "D2/F#", "Esus", "Dmaj7"]]
    return None


def lyric_progression_fallbacks(chordpro_file: Path) -> tuple[list[str], list[str]]:
    first: list[str] = []
    last: list[str] = []
    for raw_line in chordpro_file.read_text(encoding="utf-8-sig").splitlines():
        if DIRECTIVE_RE.match(raw_line) or is_progression_only_line(raw_line):
            continue
        if raw_line.startswith("CCLI Song #") or raw_line.startswith("© ") or raw_line.startswith("For use solely"):
            break
        chords = real_chords_in_line(raw_line)
        lyric_text = re.sub(r"\([^)]*\)", "", CHORD_RE.sub("", raw_line))
        if chords and TOKEN_RE.search(lyric_text):
            if not first:
                first = chords
            last = chords
    return first, last


def generate_spec(
    pro_file: Path,
    chordpro_file: Path,
    notation: int,
    skip_title: bool,
    metadata_key: str | None = None,
) -> tuple[dict, list[str]]:
    pres = load(pro_file)
    _, chart_tokens, chart_events, progressions = parse_chordpro(chordpro_file)
    title = normalized_title(pres.name)
    records = slide_records(pres)
    spec: dict[str, object] = {"_notation": notation}
    key = metadata_key or chordpro_key(chordpro_file)
    if key:
        spec["_key"] = key
    warnings = []
    matched_ranges: dict[int, list[dict]] = {}

    chart_cursor = 0
    for record in ordered_slide_records(pres, records):
        slide_tokens = tokenize(record.plain)
        if skip_title and normalized_title(record.plain) == title:
            continue
        match_start = find_match_from(slide_tokens, chart_tokens, chart_cursor)
        if match_start is None:
            match_start = find_match(slide_tokens, chart_tokens)
        if match_start is None:
            warnings.append(f"slide {record.index}: no ChordPro lyric match for {record.plain!r}")
            continue

        match_end = match_start + len(slide_tokens)
        if match_start >= chart_cursor:
            chart_cursor = match_end
        raw_chords = []
        for event in chart_events:
            if event.token_index is None or not (match_start <= event.token_index < match_end):
                continue
            slide_token = slide_tokens[event.token_index - match_start]
            raw_chords.append(
                {
                    "start": offset_in_token(slide_token, event.token_offset),
                    "chord": event.chord,
                }
            )
        if not raw_chords:
            previous_events = [event for event in chart_events if event.token_index is not None and event.token_index < match_start]
            if previous_events:
                previous_event = previous_events[-1]
                if match_start - previous_event.token_index <= 2:
                    raw_chords.append({"start": 0, "chord": previous_event.chord})
        ranges = build_ranges(record.plain, raw_chords)
        if ranges:
            spec[str(record.index)] = ranges
            matched_ranges[record.index] = ranges
        else:
            warnings.append(f"slide {record.index}: matched lyrics but found no chords")

    first_lyric_chords, last_lyric_chords = lyric_progression_fallbacks(chordpro_file)

    intro_progression = choose_progression(progressions, ("intro", "instrumental", "turnaround"), "first")
    ending_progression = choose_progression(progressions, ("ending", "outro", "last"), "last")
    intro_lines = intro_progression.lines if intro_progression else chunked_progression(first_lyric_chords)
    ending_lines = ending_progression.lines if ending_progression else chunked_progression(last_lyric_chords)

    for target in group_targets(pres, records, "intro", title):
        lines = song_progression_override(pres.name, "intro") or intro_lines
        if lines:
            spec[str(target.index)] = progression_entry(lines, target.plain)
    for target in group_targets(pres, records, "ending", title):
        lines = song_progression_override(pres.name, "ending") or ending_lines
        if lines:
            spec[str(target.index)] = progression_entry(lines, target.plain)
    filled_indices = {int(key) for key in spec if not str(key).startswith("_")}
    warnings = [
        warning
        for warning in warnings
        if not (match := re.match(r"slide (\d+):", warning)) or int(match.group(1)) not in filled_indices
    ]
    return spec, warnings


def main():
    parser = argparse.ArgumentParser(description="Match ChordPro text to a ProPresenter file")
    parser.add_argument("pro_file", type=Path)
    parser.add_argument("chordpro_file", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--notation", type=int, default=0, choices=[0, 1, 2, 3])
    parser.add_argument("--include-title", action="store_true")
    parser.add_argument("--metadata-key", help="override the ProPresenter music key metadata written to the JSON spec")
    args = parser.parse_args()

    spec, warnings = generate_spec(
        args.pro_file,
        args.chordpro_file,
        args.notation,
        not args.include_title,
        args.metadata_key,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(spec, indent=2) + "\n")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    chord_count = sum(
        len(value.get("chords", [])) if isinstance(value, dict) else len(value)
        for key, value in spec.items()
        if not key.startswith("_")
    )
    print(f"wrote {chord_count} chord(s) -> {args.output_json}")


if __name__ == "__main__":
    main()