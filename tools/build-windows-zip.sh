#!/bin/zsh
# Build the portable FoldCV Windows zip (x64, no installer, no signature) from this checkout on a Mac in one go.
# Usage: tools/build-windows-zip.sh — the result goes to output/foldcv-windows-<version>-<commit>/.
# Needs arm64 Node 22 (FOLDCV_NODE, else the newest nvm v22 or node on PATH) and python.org Python 3.13
# (FOLDCV_PYTHON). Nothing Windows runs here: the CI workflow .github/workflows/windows.yml checks the zip on Windows.
set -euo pipefail

ROOT=${0:A:h:h}
cd "$ROOT"
step() { print -P "%B==> $1%b" }
fail() { print -u2 "build-windows-zip: $1"; exit 1 }

NODE=""
for candidate in ${FOLDCV_NODE:-} $HOME/.nvm/versions/node/v22.*/bin/node(NnOn) ${commands[node]:-}; do
  if [[ -x $candidate && $($candidate -p 'process.versions.node.split(".")[0]') == 22 ]]; then
    NODE=$candidate; break
  fi
done
[[ -n $NODE ]] || fail "Node 22 is missing; install it with nvm or set FOLDCV_NODE"
export PATH="${NODE:h}:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON=${FOLDCV_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}
[[ -x $PYTHON && $($PYTHON -c 'import sys; print(sys.version_info[:2] == (3, 13))') == True ]] \
  || fail "Python 3.13 is missing; install it from python.org or set FOLDCV_PYTHON"

VERSION=$(node -p 'require("./apps/desktop/package.json").version')
COMMIT=$(git rev-parse --short HEAD)
[[ -z $(git status --porcelain) ]] || COMMIT+="-dirty"
OUTPUT="$ROOT/output/foldcv-windows-$VERSION-$COMMIT"
WORK=$(mktemp -d /private/tmp/foldcv-build-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

step "Python build environment"
# Only pip and certifi are used; the macOS build shares this environment.
VENV="$ROOT/.tools/desktop-python"
STAMP=$(cat requirements.txt requirements-service.txt requirements-desktop.txt | shasum -a 256 | cut -d' ' -f1)
if [[ ! -x $VENV/bin/python || $(cat "$VENV/.requirements" 2>/dev/null) != "$STAMP" ]]; then
  rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r requirements-desktop.txt
  print -r -- "$STAMP" > "$VENV/.requirements"
fi

# npm ci only when the lockfile changed, so a running dev server keeps its node_modules.
npm_install() {
  local stamp="$1/node_modules/.foldcv-lock" hash=$(shasum -a 256 "$1/package-lock.json" | cut -d' ' -f1)
  [[ $(cat "$stamp" 2>/dev/null) == "$hash" ]] && return
  (cd "$1" && ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --no-audit --no-fund --loglevel=error)
  print -r -- "$hash" > "$stamp"
}

step "Web frontend"
npm_install apps/web
(cd apps/web && npm run --silent build)

step "Desktop shell"
npm_install apps/desktop
(cd apps/desktop && npm run --silent typecheck && npm test --silent)

step "Windows helper"
HELPER=$("$VENV/bin/python" tools/desktop/build_windows_helper.py "$WORK/helper" | tail -1)

step "App and zip"
# An earlier build of the same version and commit is replaced.
rm -rf "$OUTPUT"
(cd apps/desktop && node scripts/package-windows.mjs "$HELPER" "$OUTPUT")
print -P "%BDone:%b $OUTPUT"
print "SHA-256 $(node -p "require('$OUTPUT/build-info.json').zipSha256")"
