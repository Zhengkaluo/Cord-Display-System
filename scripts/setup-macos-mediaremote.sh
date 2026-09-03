#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
tool_prefix="$project_root/.tools/nowplaying-cli"
source_url="https://github.com/kirtan-shah/nowplaying-cli.git"
source_tag="v2.1.0"
expected_commit="8c8c1fa4820681fd4bbd6a17ce0a5655e1f4ebe7"
build_root="$(mktemp -d "${TMPDIR:-/tmp}/cord-nowplaying.XXXXXX")"

cleanup() {
  rm -rf "$build_root"
}
trap cleanup EXIT

echo "Downloading nowplaying-cli $source_tag..."
git clone --depth 1 --branch "$source_tag" "$source_url" "$build_root/source"

actual_commit="$(git -C "$build_root/source" rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "Unexpected source commit: $actual_commit" >&2
  exit 1
fi

echo "Building project-local MediaRemote helper..."
make -C "$build_root/source"
make -C "$build_root/source" install PREFIX="$tool_prefix"

echo "Installed: $tool_prefix/bin/nowplaying-cli"
echo "The tool remains local to Cord Display System."
