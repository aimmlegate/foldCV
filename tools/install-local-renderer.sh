#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/.tools/LibreOffice.app"
URL="https://download.documentfoundation.org/libreoffice/stable/26.2.6/mac/aarch64/LibreOffice_26.2.6_MacOS_aarch64.dmg"
EXPECTED="94bb3248df074c225490a8a6d1d9dc87c7d6783dbb7a8e9f0d0c3d94348552af"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Pinned renderer supports macOS arm64 only" >&2
  exit 1
fi

if [[ ! -x "$APP/Contents/MacOS/soffice" ]]; then
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/foldcv-lo.XXXXXX")"
  trap 'hdiutil detach "$WORK/mount" -quiet 2>/dev/null || true; rm -rf "$WORK"' EXIT
  mkdir "$WORK/mount"
  curl --fail --location --silent --show-error "$URL" --output "$WORK/LibreOffice.dmg"
  ACTUAL="$(shasum -a 256 "$WORK/LibreOffice.dmg" | awk '{print $1}')"
  if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    echo "LibreOffice image checksum mismatch" >&2
    exit 1
  fi
  hdiutil attach "$WORK/LibreOffice.dmg" -nobrowse -readonly -mountpoint "$WORK/mount" -quiet
  mkdir -p "$ROOT/.tools"
  cp -R "$WORK/mount/LibreOffice.app" "$APP"
  hdiutil detach "$WORK/mount" -quiet
fi

FONTS="$APP/Contents/Resources/fonts/truetype"
mkdir -p "$FONTS"
cp "$ROOT"/skills/format-resume/assets/fonts/SourceSansPro-*.ttf "$FONTS/"
VERSION="$("$APP/Contents/MacOS/soffice" --version)"
if [[ "$VERSION" != "LibreOffice 26.2.6.3 "* ]]; then
  echo "Wrong LibreOffice version: $VERSION" >&2
  exit 1
fi
echo "$VERSION"
