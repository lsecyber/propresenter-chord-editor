#!/usr/bin/env python3
"""Read and write chords in ProPresenter 7 (.pro) files.

A .pro file is a binary protobuf. Chords are structured attributes attached to
character ranges in the lyric text, not inline ChordPro markers.

Usage:
    python prochords.py list   song.pro
    python prochords.py dump   song.pro
    python prochords.py add    song.pro out.pro --json chords.json
    python prochords.py clear  song.pro out.pro
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "pb"))
try:
    import presentation_pb2
except ImportError:
    sys.exit(
        "Compiled protobuf modules not found.\n"
        "Run ./build_protos.sh first (needs grpcio-tools and protobuf)."
    )


def rtf_to_plain(rtf: bytes) -> str:
    """Extract visible lyric text from a macOS RTF blob."""
    from striprtf.striprtf import rtf_to_text

    return rtf_to_text(rtf.decode("utf-8", "replace"))


def plain_to_rtf(plain: str) -> bytes:
    """Build a minimal centered macOS RTF blob for generated placeholder text."""

    def escape_char(char: str) -> str:
        if char == "\n":
            return "\\\n"
        if char == "\\":
            return "\\\\"
        if char == "{":
            return "\\{"
        if char == "}":
            return "\\}"
        codepoint = ord(char)
        if codepoint > 127:
            if codepoint > 32767:
                codepoint -= 65536
            return f"\\uc0\\u{codepoint} "
        return char

    escaped = "".join(escape_char(char) for char in plain)
    rtf = (
        "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2867\n"
        "\\cocoatextscaling0\\cocoaplatform0{\\fonttbl\\f0\\fnil\\fcharset0 Helvetica;}\n"
        "{\\colortbl;\\red255\\green255\\blue255;\\red255\\green255\\blue255;}\n"
        "{\\*\\expandedcolortbl;;}\n"
        "\\pard\\pardirnatural\\qc\\partightenfactor0\n\n"
        f"\\f0\\fs120 \\cf2 {escaped} }}"
    )
    return rtf.encode("utf-8")


def rtf_escape_text(text: str) -> str:
    def escape_char(char: str) -> str:
        if char == "\n":
            return "\\\n"
        if char == "\\":
            return "\\\\"
        if char == "{":
            return "\\{"
        if char == "}":
            return "\\}"
        codepoint = ord(char)
        if codepoint > 127:
            if codepoint > 32767:
                codepoint -= 65536
            return f"\\uc0\\u{codepoint} "
        return char

    return "".join(escape_char(char) for char in text)


def append_plain_text_to_rtf(rtf: bytes, text: str) -> bytes:
    if not text:
        return rtf
    source = rtf.decode("utf-8", "replace")
    insert_at = source.rfind("}")
    if insert_at == -1:
        raise ValueError("RTF data does not contain a closing brace")
    return (source[:insert_at] + rtf_escape_text(text) + source[insert_at:]).encode("utf-8")


def prepend_plain_text_to_rtf(rtf: bytes, text: str) -> bytes:
    if not text:
        return rtf
    source = rtf.decode("utf-8", "replace")
    insert_at = source.find("\n\n")
    if insert_at == -1:
        return plain_to_rtf(text + rtf_to_plain(rtf))
    insert_at += 2
    return (source[:insert_at] + rtf_escape_text(text) + source[insert_at:]).encode("utf-8")


def iter_text_elements(pres):
    """Yield (slide_index, text_message) for the first text element on each slide."""
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
                    yield slide_index, element.text
                    break
            break


def load(path: str | Path):
    pres = presentation_pb2.Presentation()
    pres.ParseFromString(Path(path).read_bytes())
    return pres


KEY_ENUMS = {
    "AB": 0,
    "A": 1,
    "A#": 2,
    "BB": 3,
    "B": 4,
    "B#": 5,
    "CB": 6,
    "C": 7,
    "C#": 8,
    "DB": 9,
    "D": 10,
    "D#": 11,
    "EB": 12,
    "E": 13,
    "E#": 14,
    "FB": 15,
    "F": 16,
    "F#": 17,
    "GB": 18,
    "G": 19,
    "G#": 20,
}


def normalize_music_key(key: str) -> tuple[str, int] | None:
    cleaned = key.strip().replace("♭", "b").replace("♯", "#")
    if not cleaned:
        return None
    normalized = cleaned[0].upper() + cleaned[1:]
    enum_key = normalized.upper()
    if enum_key not in KEY_ENUMS:
        return None
    return normalized, KEY_ENUMS[enum_key]


def set_music_key(pres, key: str) -> None:
    normalized = normalize_music_key(key)
    if normalized is None:
        print(f"warning: unsupported music key {key!r}, leaving key metadata unchanged", file=sys.stderr)
        return
    key_name, key_enum = normalized
    pres.music_key = key_name
    pres.music.original_music_key = key_name
    pres.music.user_music_key = key_name
    pres.music.original.music_key = key_enum
    pres.music.original.music_scale = 0
    pres.music.user.music_key = key_enum
    pres.music.user.music_scale = 0


def existing_chords(text):
    chords = []
    for custom_attribute in text.attributes.custom_attributes:
        if custom_attribute.WhichOneof("Attribute") == "chord":
            chords.append(
                (
                    custom_attribute.range.start,
                    custom_attribute.range.end,
                    custom_attribute.chord,
                )
            )
    return chords


def remove_chords(text) -> int:
    keep = [
        custom_attribute
        for custom_attribute in text.attributes.custom_attributes
        if custom_attribute.WhichOneof("Attribute") != "chord"
    ]
    removed = len(text.attributes.custom_attributes) - len(keep)
    del text.attributes.custom_attributes[:]
    text.attributes.custom_attributes.extend(keep)
    return removed


def cmd_list(args):
    pres = load(args.infile)
    print(f"name: {pres.name}")
    total_slides = 0
    total_chords = 0
    for index, text in iter_text_elements(pres):
        total_slides += 1
        count = len(existing_chords(text))
        total_chords += count
        flag = " (audience chord render ON)" if text.HasField("chord_pro") and text.chord_pro.enabled else ""
        print(f"  slide {index}: {count} chord(s){flag}")
    print(f"total slides with text: {total_slides} | total chords: {total_chords}")


def cmd_dump(args):
    pres = load(args.infile)
    print(f"name: {pres.name}\n")
    for index, text in iter_text_elements(pres):
        plain = rtf_to_plain(bytes(text.rtf_data)).rstrip("\n")
        print(f"=== slide {index} ===")
        position = 0
        for line in plain.split("\n"):
            print(f"  [{position:>3}] {line!r}")
            position += len(line) + 1
        chords = existing_chords(text)
        if chords:
            for start, end, chord in chords:
                snippet = plain[start:end].replace("\n", "\\n")
                print(f"        chord [{start}:{end}] = {chord!r} over {snippet!r}")
        else:
            print("        (no chords)")
        print()


def cmd_add(args):
    pres = load(args.infile)
    spec = json.loads(Path(args.json).read_text())
    notation = int(spec.get("_notation", 0)) if isinstance(spec, dict) else 0
    if isinstance(spec, dict) and spec.get("_key"):
        set_music_key(pres, str(spec["_key"]))

    texts = {index: text for index, text in iter_text_elements(pres)}
    added = 0
    replaced = 0
    for key, entry in spec.items():
        if str(key).startswith("_"):
            continue
        index = int(key)
        if index not in texts:
            print(f"warning: slide {index} has no text element, skipping", file=sys.stderr)
            continue

        text = texts[index]
        chords = entry
        if isinstance(entry, dict):
            append_text = str(entry.get("append_text", ""))
            prepend_text = str(entry.get("prepend_text", ""))
            if "text" in entry:
                text.rtf_data = plain_to_rtf(str(entry["text"]))
            elif prepend_text:
                text.rtf_data = prepend_plain_text_to_rtf(bytes(text.rtf_data), prepend_text)
            elif append_text:
                text.rtf_data = append_plain_text_to_rtf(bytes(text.rtf_data), append_text)
            chords = entry.get("chords", [])
        if args.replace:
            replaced += remove_chords(text)
        for chord in chords:
            custom_attribute = text.attributes.custom_attributes.add()
            custom_attribute.range.start = int(chord["start"])
            custom_attribute.range.end = int(chord["end"])
            custom_attribute.chord = str(chord["chord"])
            added += 1
        text.chord_pro.enabled = bool(args.audience_chords)
        text.chord_pro.notation = notation

    Path(args.outfile).write_bytes(pres.SerializeToString())
    print(f"added {added} chord(s), replaced {replaced} -> {args.outfile}")


def cmd_clear(args):
    pres = load(args.infile)
    removed = 0
    for _, text in iter_text_elements(pres):
        removed += remove_chords(text)
        if text.HasField("chord_pro"):
            text.chord_pro.enabled = False
    Path(args.outfile).write_bytes(pres.SerializeToString())
    print(f"removed {removed} chord(s) -> {args.outfile}")


def main():
    parser = argparse.ArgumentParser(description="Read/write chords in ProPresenter 7 .pro files")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    list_parser = subparsers.add_parser("list", help="summarize chords per slide")
    list_parser.add_argument("infile")
    list_parser.set_defaults(func=cmd_list)

    dump_parser = subparsers.add_parser("dump", help="print lyric text and chords per slide")
    dump_parser.add_argument("infile")
    dump_parser.set_defaults(func=cmd_dump)

    add_parser = subparsers.add_parser("add", help="add chords from a JSON spec")
    add_parser.add_argument("infile")
    add_parser.add_argument("outfile")
    add_parser.add_argument("--json", required=True, help="chord spec file")
    add_parser.add_argument("--replace", action="store_true", help="replace existing chord attributes")
    add_parser.add_argument(
        "--audience-chords",
        action="store_true",
        help="also render chords in the main lyric text element; normally leave this off for stage-only chords",
    )
    add_parser.set_defaults(func=cmd_add)

    clear_parser = subparsers.add_parser("clear", help="remove all chords")
    clear_parser.add_argument("infile")
    clear_parser.add_argument("outfile")
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()