# ProPresenter Chord Editor

Command-line tools for reading, clearing, and adding stage-display chords in ProPresenter 7 `.pro` files.

This project edits binary protobuf presentation files directly. It is not affiliated with, endorsed by, or supported by Renewed Vision. Keep backups of every `.pro` file before writing changes.

## What It Does

- Lists and dumps chord attributes already stored in a ProPresenter file.
- Adds chord custom attributes from a JSON spec.
- Clears chord custom attributes without changing slide text.
- Converts a ChordPro chart into the JSON spec by matching chart lyrics to ProPresenter slide text.
- Keeps chords stage-display-only by default; audience lyric rendering is opt-in.

## Repository Hygiene

Real presentation files, ChordPro charts, generated outputs, and local backups are intentionally ignored. They can contain copyrighted song text, church-specific media, or private library metadata.

Generated protobuf Python modules are also ignored. Rebuild them from the vendored `.proto` files after installing dependencies.

## Setup

Requirements:

- Python 3.10 or newer
- A shell that can run `build_protos.sh`

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./build_protos.sh
```

By default, `build_protos.sh` compiles protobuf definitions from `vendor/ProPresenter7-Proto/Proto7.16.2` into `pb/`. Override paths when needed:

```sh
PROTO_DIR=/path/to/protos OUT_DIR=pb PYTHON=.venv/bin/python ./build_protos.sh
```

## Usage

Inspect a presentation:

```sh
python prochords.py list path/to/song.pro
python prochords.py dump path/to/song.pro
```

Generate a JSON spec from a ChordPro file:

```sh
python scripts/chordpro_to_json.py path/to/song.pro path/to/song.chordpro generated/song-chords.json
```

Write chords into a copy of the presentation:

```sh
python prochords.py add path/to/song.pro path/to/song-with-chords.pro --json generated/song-chords.json --replace
```

Remove chords from a copy of the presentation:

```sh
python prochords.py clear path/to/song.pro path/to/song-without-chords.pro
```

Use `--audience-chords` only if you also want ProPresenter to render chords in the main lyric text element. Without it, the tool leaves `chord_pro.enabled` off so chords remain stage-display-only.

## JSON Spec

The JSON input maps slide indexes to chord ranges. Ranges use zero-based offsets in the plain text extracted from the slide's RTF data.

See [examples/chords.example.json](examples/chords.example.json) for a sanitized example.

```json
{
	"_notation": 0,
	"_key": "C",
	"1": [
		{ "start": 0, "end": 8, "chord": "C" },
		{ "start": 9, "end": 17, "chord": "G" }
	]
}
```

Entries can also set or append invisible anchor text for chord-only sections such as intros, endings, and instrumentals:

```json
{
	"2": {
		"prepend_text": "\u200b\u2001\u200b\n",
		"chords": [
			{ "start": 0, "end": 1, "chord": "C" },
			{ "start": 2, "end": 3, "chord": "F" }
		]
	}
}
```

## Development Checks

```sh
.venv/bin/python -m py_compile prochords.py scripts/chordpro_to_json.py
.venv/bin/python prochords.py --help
.venv/bin/python scripts/chordpro_to_json.py --help
PYTHON=.venv/bin/python ./build_protos.sh
```

## Third-Party Code

The protobuf definitions under `vendor/ProPresenter7-Proto` are vendored from the MIT-licensed ProPresenter7-Proto project. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream license in [vendor/ProPresenter7-Proto/LICENSE](vendor/ProPresenter7-Proto/LICENSE).

## License

This project is released under the MIT License. See [LICENSE](LICENSE).