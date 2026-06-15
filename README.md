# ProPresenter Chord Editor

Add chords to ProPresenter 7 songs from the command line, in seconds, without clicking through every slide.

ProPresenter stores chords as character-range attributes inside the binary `.pro` file, and the built-in editor makes you place each one by hand. If you already have a ChordPro chart (or a key and a few chord positions), this tool writes the chords straight into the presentation for you — and keeps them on the stage display only, so your congregation never sees them unless you ask.

> Not affiliated with, endorsed by, or supported by Renewed Vision. This tool edits the `.pro` file format directly using a community-maintained, reverse-engineered schema. The format is undocumented and can change between ProPresenter versions, so **always keep a backup of any `.pro` file before writing to it.**

## What it does

- **List / dump** the chords already stored in a presentation, slide by slide.
- **Add** chords from a simple JSON spec.
- **Clear** chords without touching the slide lyrics.
- **Convert** a ChordPro chart into the JSON spec automatically, matching the chart's lyrics to the slides in your presentation.
- **Stage-display only by default.** Audience-visible chord rendering is opt-in (`--audience-chords`).

## Setup

You need **Python 3.10+** and a POSIX shell.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./build_protos.sh
```

`build_protos.sh` compiles the vendored protobuf schema into `pb/`. By default it reads `vendor/ProPresenter7-Proto/Proto7.16.2`. Override the paths if you need a different schema version or output directory:

```sh
PROTO_DIR=/path/to/protos OUT_DIR=pb PYTHON=.venv/bin/python ./build_protos.sh
```

The generated modules in `pb/` are build artifacts and are not checked in — rebuild them after cloning.

## Quick start

Inspect a presentation before changing anything:

```sh
python prochords.py list path/to/song.pro
python prochords.py dump path/to/song.pro
```

Generate a JSON spec from a ChordPro chart:

```sh
python scripts/chordpro_to_json.py path/to/song.pro path/to/song.chordpro song-chords.json
```

Write the chords into a **copy** of the presentation (never overwrite your original):

```sh
python prochords.py add path/to/song.pro song-with-chords.pro --json song-chords.json --replace
```

Remove all chords from a copy:

```sh
python prochords.py clear path/to/song.pro song-without-chords.pro
```

Add `--audience-chords` only if you want ProPresenter to render the chords in the main lyric text as well. Without it, chords stay on the stage display (`chord_pro.enabled` is left off).

## JSON spec

The spec maps each slide index to a list of chord ranges. Offsets are zero-based positions in the plain text extracted from the slide's RTF, so `start`/`end` mark which characters a chord sits above. See [examples/chords.example.json](examples/chords.example.json) for a full sample.

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

`_notation` selects the chord notation style (0–3) and `_key` sets the song's key metadata. Both are optional.

For chord-only sections like intros, endings, and instrumentals, an entry can also insert invisible anchor text to hang the chords on:

```json
{
  "2": {
    "prepend_text": "​ ​\n",
    "chords": [
      { "start": 0, "end": 1, "chord": "C" },
      { "start": 2, "end": 3, "chord": "F" }
    ]
  }
}
```

`scripts/chordpro_to_json.py` generates these automatically from the chord progressions in a ChordPro chart, so you rarely have to write them by hand.

## A note on your song files

Real presentations, ChordPro charts, generated specs, and backups are git-ignored on purpose — they often contain copyrighted lyrics, church-specific media, or private library metadata. Keep them out of any fork you publish, and use small, synthetic fixtures when contributing examples or tests.

## Development

```sh
.venv/bin/python -m py_compile prochords.py scripts/chordpro_to_json.py
.venv/bin/python prochords.py --help
.venv/bin/python scripts/chordpro_to_json.py --help
PYTHON=.venv/bin/python ./build_protos.sh
```

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Third-party code

The protobuf definitions under `vendor/ProPresenter7-Proto` are vendored from the MIT-licensed [ProPresenter7-Proto](https://github.com/greyshirtguy/ProPresenter7-Proto) project. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream [LICENSE](vendor/ProPresenter7-Proto/LICENSE).

## License

MIT — see [LICENSE](LICENSE).

ProPresenter is a trademark of Renewed Vision, LLC. It is used here only to describe compatibility, under nominative fair use.
