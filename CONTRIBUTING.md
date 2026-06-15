# Contributing

Thanks for helping make this tool safer and easier to use.

## Local Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./build_protos.sh
```

## Before Opening a Pull Request

Run the basic checks:

```sh
.venv/bin/python -m py_compile prochords.py scripts/chordpro_to_json.py
.venv/bin/python prochords.py --help
.venv/bin/python scripts/chordpro_to_json.py --help
PYTHON=.venv/bin/python ./build_protos.sh
```

## Data Safety

- Do not commit real `.pro` files, ChordPro files, song lyrics, generated outputs, or backup folders.
- Use sanitized fixtures or small synthetic examples when adding documentation or tests.
- Preserve the stage-display-only default unless a change explicitly targets audience chord rendering.
- Keep the third-party notices intact when changing vendored protobuf definitions.

## Style

Keep changes focused, readable, and close to the existing command-line style. Prefer small pure functions for parsing and matching behavior so future tests can cover them without requiring real presentations.