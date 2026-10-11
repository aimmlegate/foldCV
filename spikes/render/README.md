# Editable output spike

This spike uses only synthetic input. It writes ordinary DOCX paragraphs, tables,
and inline pictures, then converts that DOCX to PDF with the local LibreOffice
build. The PDF is never drawn by ReportLab; ReportLab measures text widths for
conservative page grouping.

Install packages into the project environment and place the licensed fonts in
the ignored local LibreOffice bundle:

```sh
.venv/bin/python -m pip install -r spikes/render/requirements.txt
.venv/bin/python spikes/render/renderer.py setup-fonts
```

The converter must be at `.tools/LibreOffice.app/Contents/MacOS/soffice`.
`setup-fonts` changes only that project-local bundle, not system font settings.
Run the fixtures and inspect all pages:

```sh
for name in short long-main long-sidebar; do
  .venv/bin/python spikes/render/renderer.py render \
    "spikes/render/fixtures/$name.json" experiments/gui-render-spike
done
.venv/bin/python -m unittest discover -s tests/render_spike -v
```

The committed page images under `tests/render_spike/baselines/` are the reviewed
synthetic reference for the pinned converter and fonts. Rendered DOCX/PDF and
review images in `experiments/gui-render-spike/` are ignored. The output fixture
footer is `Synthetic local document`; production defaults to `mail@example.com`.

The macOS shell sandbox used during development aborts headless LibreOffice with
exit 134. The real conversion and test commands were run outside that sandbox.
Missing fonts or converter fail before rendering; a conversion timeout raises an
error. Large indivisible blocks fail visibly when they exceed a page budget.
