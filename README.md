# lyx-live

Auto-rebuild a [LyX](https://www.lyx.org) document to PDF every time it changes on disk, so the PDF in your viewer is always current.

Useful when the `.lyx` is edited from outside LyX: by a script, a collaborator's sync, or an AI coding assistant. LyX itself only offers a "file changed, reload?" dialog; this gives you a live PDF instead.

- Single file, Python 3.7+ standard library only. No `fswatch`/`entr` needed.
- Your project stays clean: the PDF goes to a temp dir (or wherever you choose), not next to the source.
- Atomic PDF replacement: viewers never see a half-written file, and a failed build keeps the last good PDF.
- Debounced: waits until the file stops changing before building.
- Also watches the `.bib` files next to your document.
- Follows `\include` / `\input` (multi-file theses and books): every `.lyx` pulled in by the main document, recursively, is watched too, and newly added includes are picked up while running.

## Usage

```bash
python3 lyx_live.py paper.lyx                # build, open viewer, rebuild on change
python3 lyx_live.py paper.lyx -o out/paper.pdf
python3 lyx_live.py paper.lyx --viewer zathura
python3 lyx_live.py paper.lyx --no-open      # just keep the PDF fresh
python3 lyx_live.py paper.lyx -f pdf4        # xelatex (pdf5 = lualatex)
python3 lyx_live.py paper.lyx -w refs/extra.bib
```

Options: `-o/--output`, `-w/--watch` (repeatable, for extra files beyond the automatic ones), `-f/--format`, `-i/--interval`, `--settle`, `--viewer`, `--no-open`, `--lyx`.

## Viewer tips

Use a viewer that reloads the PDF when it changes:

| OS | Viewer |
|----|--------|
| macOS | [Skim](https://skim-app.sourceforge.io) (used automatically if installed), Preview also works but is less reliable |
| Linux | zathura, evince, okular |
| Windows | SumatraPDF |

## Notes

- Builds use `lyx -E`, which compiles in LyX's own temp directory. Figures and bibliographies resolve relative to the `.lyx` as usual.
- A build can print `LyX exit 1: warnings` and still produce a good PDF (typically unresolved citations on the first pass). A real failure prints the tail of LyX's output and keeps the previous PDF.
- LyX must be installed. It is found on `PATH`, in the default macOS/Windows locations, or via `--lyx`.
- A full build with bibliography takes several seconds for a paper; that is the lag you will see.

## License

MIT
