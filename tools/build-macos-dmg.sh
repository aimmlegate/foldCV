#!/bin/zsh
# Build the FoldCV macOS app and its DMG from this checkout in one go (Apple Silicon, ad-hoc signature): the frontend,
# the service frozen with PyInstaller and the Tauri window of apps/desktop-tauri around them.
# Usage: tools/build-macos-dmg.sh — the result goes to output/foldcv-macos-<version>-<commit>/.
# FOLDCV_PUBLIC_TEMPLATES=1 builds without the private templates in templates/local.
# Needs arm64 Node 22 (FOLDCV_NODE, else the newest nvm v22 or node on PATH), python.org Python 3.13 (FOLDCV_PYTHON)
# and Rust from rustup (FOLDCV_CARGO, else ~/.cargo/bin/cargo). The first run downloads Python packages, npm packages
# and crates into .tools, node_modules and ~/.cargo.
set -euo pipefail

ROOT=${0:A:h:h}
cd "$ROOT"
step() { print -P "%B==> $1%b" }
fail() { print -u2 "build-macos-dmg: $1"; exit 1 }

[[ $(uname -m) == arm64 ]] || fail "this script builds on Apple Silicon only"

NODE=""
for candidate in ${FOLDCV_NODE:-} $HOME/.nvm/versions/node/v22.*/bin/node(NnOn) ${commands[node]:-}; do
  if [[ -x $candidate && $($candidate -p 'process.arch + process.versions.node.split(".")[0]') == arm6422 ]]; then
    NODE=$candidate; break
  fi
done
[[ -n $NODE ]] || fail "arm64 Node 22 is missing; install it with nvm or set FOLDCV_NODE"
CARGO=${FOLDCV_CARGO:-$HOME/.cargo/bin/cargo}
[[ -x $CARGO ]] || fail "cargo is missing; install Rust with rustup or set FOLDCV_CARGO"
export PATH="${NODE:h}:${CARGO:h}:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON=${FOLDCV_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}
[[ -x $PYTHON && $($PYTHON -c 'import sys; print(sys.version_info[:2] == (3, 13))') == True ]] \
  || fail "Python 3.13 is missing; install it from python.org or set FOLDCV_PYTHON"

NAME="foldCV Beta"
# Monterey is the oldest macOS whose Safari updates bring the WebKit the page needs (pdf.js: Safari 17.4).
MINIMUM_MACOS=12.0
VERSION=$(node -p 'require("./apps/desktop-tauri/tauri.conf.json").version')
TAURI=$(awk '/^name = "tauri"$/ { found = 1; next } found { gsub(/[^0-9.]/, ""); print; exit }' apps/desktop-tauri/Cargo.lock)
COMMIT=$(git rev-parse --short HEAD)
[[ -z $(git status --porcelain) ]] || COMMIT+="-dirty"
OUTPUT="$ROOT/output/foldcv-macos-$VERSION-$COMMIT"
WORK=$(mktemp -d /private/tmp/foldcv-build-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

step "Python build environment"
VENV="$ROOT/.tools/desktop-python"
STAMP=$(cat requirements.txt requirements-service.txt requirements-desktop.txt | shasum -a 256 | cut -d' ' -f1)
if [[ ! -x $VENV/bin/python || $(cat "$VENV/.requirements" 2>/dev/null) != "$STAMP" ]]; then
  rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r requirements-desktop.txt
  print -r -- "$STAMP" > "$VENV/.requirements"
fi

step "Web frontend"
stamp="apps/web/node_modules/.foldcv-lock" hash=$(shasum -a 256 apps/web/package-lock.json | cut -d' ' -f1)
if [[ $(cat "$stamp" 2>/dev/null) != "$hash" ]]; then
  (cd apps/web && npm ci --no-audit --no-fund --loglevel=error)
  print -r -- "$hash" > "$stamp"
fi
(cd apps/web && npm run --silent build)

step "Tauri shell"
(cd apps/desktop-tauri && cargo test --release --locked --quiet && cargo build --release --locked --quiet)

step "Helper"
HELPER=$("$VENV/bin/python" tools/desktop/build_helper.py "$WORK/helper" | tail -1)
"$VENV/bin/python" tools/desktop/check_helper.py "$HELPER"

step "App and DMG"
# An earlier build of the same version and commit is replaced.
rm -rf "$OUTPUT"
APP="$OUTPUT/$NAME.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/en.lproj" "$APP/Contents/Resources/ru.lproj"
cp apps/desktop-tauri/target/release/foldcv-beta "$APP/Contents/MacOS/$NAME"
cp assets/branding/foldcv/liquid-glass-v2/macos/FoldCV-native-olive.icns "$APP/Contents/Resources/FoldCV.icns"
# ditto keeps the helper's relative links, modes and signatures.
ditto "$HELPER" "$APP/Contents/Helpers/FoldCV Helper.app"
PLIST="$APP/Contents/Info.plist"
plutil -create xml1 "$PLIST"
for key value in CFBundleDevelopmentRegion en CFBundleDisplayName "$NAME" CFBundleExecutable "$NAME" \
    CFBundleIconFile FoldCV.icns CFBundleIdentifier invalid.foldcv.beta CFBundleInfoDictionaryVersion 6.0 \
    CFBundleName "$NAME" CFBundlePackageType APPL CFBundleShortVersionString "$VERSION" CFBundleVersion "$VERSION" \
    LSApplicationCategoryType public.app-category.productivity LSMinimumSystemVersion "$MINIMUM_MACOS"; do
  plutil -insert "$key" -string "$value" "$PLIST"
done
plutil -insert NSHumanReadableCopyright -string "Copyright © 2026 FoldCV authors. GNU AGPL v3 or later." "$PLIST"
cp LICENSE "$APP/Contents/Resources/LICENSE.txt"
cp THIRD-PARTY-NOTICES.md "$APP/Contents/Resources/THIRD-PARTY-NOTICES.md"
for key in NSHighResolutionCapable NSSupportsAutomaticGraphicsSwitching; do plutil -insert "$key" -bool YES "$PLIST"; done
for key in NSQuitAlwaysKeepsWindows NSRequiresAquaSystemAppearance; do plutil -insert "$key" -bool NO "$PLIST"; done
# With the ru and en folders, this list lets the system's own panels, such as the save dialog, speak the user's language.
plutil -insert CFBundleLocalizations -json '["en","ru"]' "$PLIST"
plutil -insert NSAppTransportSecurity -json '{"NSAllowsLocalNetworking":true}' "$PLIST"
plutil -lint -s "$PLIST"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

VOLUME="$WORK/volume" MOUNT="$WORK/mount" DMG="$OUTPUT/$NAME $VERSION.dmg"
mkdir "$VOLUME"
ditto "$APP" "$VOLUME/$NAME.app"
ln -s /Applications "$VOLUME/Applications"
cp LICENSE "$VOLUME/LICENSE.txt"
cp THIRD-PARTY-NOTICES.md "$VOLUME/THIRD-PARTY-NOTICES.md"
hdiutil create -quiet -volname "$NAME $VERSION" -fs HFS+ -format UDZO -srcfolder "$VOLUME" "$DMG"
hdiutil verify -quiet "$DMG"
hdiutil attach -quiet -nobrowse -readonly -mountpoint "$MOUNT" "$DMG"
{ codesign --verify --deep --strict "$MOUNT/$NAME.app" } always { hdiutil detach -quiet "$MOUNT" }

SHA=$(shasum -a 256 "$DMG" | cut -d' ' -f1)
NAME="$NAME" VERSION="$VERSION" TAURI="$TAURI" MINIMUM="$MINIMUM_MACOS" DMG="$DMG" SHA="$SHA" DIRTY=$([[ $COMMIT == *-dirty ]] && print true || print false) \
  node -e 'const { env } = process, fs = require("fs"), path = require("path");
fs.writeFileSync(path.join(path.dirname(env.DMG), "build-info.json"), JSON.stringify({ application: env.NAME,
  version: env.VERSION, commit: require("child_process").execSync("git rev-parse HEAD").toString().trim(),
  dirty: env.DIRTY === "true", shell: "tauri", tauri: env.TAURI, minimumSystemVersion: env.MINIMUM,
  dmg: path.basename(env.DMG), dmgBytes: fs.statSync(env.DMG).size, dmgSha256: env.SHA, signature: "ad-hoc",
  builtAt: new Date().toISOString() }, null, 2) + "\n");'
print -P "%BDone:%b $OUTPUT"
print "SHA-256 $SHA"
