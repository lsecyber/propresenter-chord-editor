#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_bin=${PYTHON:-python3}
proto_dir=${PROTO_DIR:-"$script_dir/vendor/ProPresenter7-Proto/Proto7.16.2"}
out_dir=${OUT_DIR:-"$script_dir/pb"}

if [ ! -d "$proto_dir" ]; then
  echo "Proto directory not found: $proto_dir" >&2
  exit 1
fi

mkdir -p "$out_dir"
"$python_bin" -m grpc_tools.protoc \
  -I "$proto_dir" \
  --python_out="$out_dir" \
  "$proto_dir"/*.proto

echo "compiled protobuf modules into $out_dir"