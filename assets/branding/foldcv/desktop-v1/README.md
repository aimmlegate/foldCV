# FoldCV desktop assets

Proposed exports of the mark already used in the workbench. No application files
or release selections are changed.

The mark comes from `design/future-editor/visual/icons.svg#i-fold`; colors come
from `design/future-editor/visual/tokens.css`. The folded-sheet path is unchanged.
The former ReCV concepts and old magenta `assets/icon.svg` are not the source.

- `preview.png`: overview, including small icon sizes.
- `source/`: editable SVG artwork, with transparent mark and wordmark variants.
- `png/`: raster exports; the main icon is 1024 × 1024 with transparent margins.
- `macos/FoldCV.icns`: native macOS icon, including 16–1024 px representations.
- `macos/FoldCV.iconset/`: source PNG representations for the native icon.
- `web/`: SVG, PNG and ICO favicons with heavier strokes at small sizes.
- `png/empty-state.png`: transparent 960 × 640 illustration.
- `png/dmg-background.png`: 660 × 440 installer background.
- `macos/dmg-background@2x.png`: 1320 × 880 installer background.
- `manifest.json`: source references, palette and file hashes.

DMG layout: use a 660 × 440 content area, 80 px native icons centered near
(190, 232) and (470, 232), with the application on the left and Applications
alias on the right. The background contains the connecting arrow and Russian
instruction only; Finder supplies the actual icons and file names. Confirm their
positions in a packaged DMG before release.

SVG wordmarks retain editable text. They use Helvetica Neue with Arial fallback;
PNG exports fix the rendered appearance. The UI keeps its existing system font.

Rebuild on macOS with `python3 assets/branding/foldcv/desktop-v1/export_assets.py`.
Requires `rsvg-convert` and the system `iconutil`. Exporting needs no model call.
