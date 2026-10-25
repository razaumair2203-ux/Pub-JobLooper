# Brand assets

- `app-mark.svg` is the canonical large Joblooper mark used in documentation.
- `dashboard/app-icon.svg` is the generated compact mark used by the dashboard,
  browser tab and launcher icon pipeline.
- `joblooper.ico.b64` is generated operating-system launcher data.
- `parrot-source.png` is private source material and is intentionally ignored;
  it is not a distributable product asset.
- `archive/` contains retired collateral for provenance only. Files in it are
  not current brand references and are not included in the public mirror.

Do not hand-edit generated icon derivatives. Run `python tools/build_app_icon.py`
after an approved change to the canonical source and use `--check` in review.
