# FoldCV Liquid Glass study

Two material treatments of the current FoldCV mark: olive glass and light frosted
glass. The geometry comes directly from `design/future-editor/visual/icons.svg#i-fold`.
The original v1 exports and application files remain unchanged.

- `native-preview.png`: Apple-rendered variants and six system appearances.
- `preview.png`: earlier SVG material studies, including small sizes.
- `source/`: editable SVG studies for the icons, illustration and DMG background.
- `png/`: static renders; icon canvases are 1024 × 1024 with transparent margins.
- `macos/FoldCV-*-glass.icon`: editable native Icon Composer sources.
- `macos/FoldCV-*-glass Exports/`: six native PNG appearance renders per variant.
- `macos/FoldCV-native-*.icns`: static fallbacks built from Apple-rendered PNGs.
- `macos/FoldCV-*-glass.icns`: earlier static SVG material studies.
- `macos/`: also includes iconsets and a Retina DMG background.
- `layers/`: clean 1024 × 1024 SVG/PNG inputs for Icon Composer. Backgrounds are
  full square and opaque; foregrounds are transparent. These inputs do not bake
  in masks, highlights, refraction or shadows.
- `manifest.json`: source reference and hashes.

Both native `.icon` sources were opened in Apple Icon Composer 27.0, with glass
effects enabled on the imported mark. Six appearances were exported for each:
Default, Dark, Clear Light, Clear Dark, Tinted Light and Tinted Dark. The source
uses the shared square composition for iOS and macOS; Composer labels those
shared-square PNG exports `iOS`. Do not treat that filename as native Dock proof.

The native foreground is the original mark SVG with no baked material effects.
The olive source uses a paper-colored mark over the brand olive background; the
frosted source uses an olive mark over a light background. Edit those layers in
Composer to adjust the system material. Do not import the complete baked PNG
icon as a foreground, as that would duplicate lighting and masking.

PNG and ICNS remain static images. Only the `.icon` sources retain native layers.
The native ICNS fallbacks place the Apple-rendered Default appearance within
100 px transparent margins on a 1024 px canvas. Electron integration, packaging
and actual Dock appearance behavior have not been tested or changed.

The wordmark and small interface controls keep their current flat appearance.
The supporting illustration and installer background use restrained material depth.
For the DMG, use the v1 layout: 660 × 440 content area, 80 px native icons centered
at (190, 232) and (470, 232). Confirm placement in the packaged installer.

Rebuild on macOS with `python3 assets/branding/foldcv/liquid-glass-v2/export_assets.py`.
Requires `rsvg-convert` and the system `iconutil`.
The script preserves native sources and appearance exports, then repackages them
with `package_native.py`. To update native renders, export all appearances again
from Composer before rebuilding the package.

References: [Icon Composer](https://developer.apple.com/icon-composer/) and
[Apple app icon guidance](https://developer.apple.com/design/human-interface-guidelines/app-icons/).
