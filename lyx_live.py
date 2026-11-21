#!/usr/bin/env python3
"""lyx-live: rebuild a LyX document to PDF whenever it changes on disk.

Edit the .lyx (by hand, with a script, with an AI assistant ...) and the PDF
in your viewer refreshes by itself.  Standard library only.

    python3 lyx_live.py paper.lyx
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LYX_CANDIDATES = [
    "/Applications/LyX.app/Contents/MacOS/lyx",  # macOS
    "C:/Program Files/LyX 2.4/bin/lyx.exe",      # Windows
]


def find_lyx(explicit):
    if explicit:
        return explicit
    found = shutil.which("lyx")
    if found:
        return found
    for cand in LYX_CANDIDATES:
        if os.path.exists(cand):
            return cand
    sys.exit("error: LyX not found. Put it on PATH or pass --lyx /path/to/lyx")


_INCLUDE_RE = re.compile(
    r'^\\begin_inset CommandInset (?:include|input)\s*\n'
    r'(?:[^\n]*\n)*?filename "([^"]+)"', re.M)


def find_includes(src, seen=None):
    """Recursively collect .lyx files pulled in via \\include / \\input.

    LyX stores these as `CommandInset include` blocks with a `filename`
    relative to the including document.  Non-.lyx files (e.g. .tex) are
    skipped; missing files are ignored.
    """
    seen = set() if seen is None else seen
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for name in _INCLUDE_RE.findall(text):
        child = (src.parent / name).resolve()
        if child.suffix == ".lyx" and child.is_file() and child not in seen:
            seen.add(child)
            out.append(child)
            out.extend(find_includes(child, seen))
    return out


def watch_list(src, extra):
    """Main file + included chapters + extras + .bib files next to the main file."""
    files = [src] + find_includes(src, {src}) + list(extra)
    files += sorted(src.parent.glob("*.bib"))
    return list(dict.fromkeys(files))  # dedupe, keep order


def stamp(paths):
    """Cheap change detector: (mtime, size) of every watched file."""
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append((str(p), st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            out.append((str(p), 0, 0))
    return tuple(out)


def build(lyx, src, pdf, fmt):
    """Export to a temp file, then atomically replace `pdf`.

    Viewers never see a half-written PDF, and a failed build keeps the
    last good PDF on screen.  `lyx -E` compiles in LyX's own temp dir, so
    nothing is written next to the source.
    """
    tmp = pdf.with_name(".building-" + pdf.name)
    if tmp.exists():
        tmp.unlink()
    t0 = time.time()
    proc = subprocess.run(
        [lyx, "-E", fmt, str(tmp), str(src)],
        capture_output=True, text=True, cwd=src.parent,
    )
    ok = tmp.exists() and tmp.stat().st_size > 0
    if ok:
        os.replace(tmp, pdf)
    dt = time.time() - t0
    if ok and proc.returncode == 0:
        print(f"[{time.strftime('%H:%M:%S')}] built in {dt:.1f}s")
    elif ok:
        # e.g. pdflatex warnings about unresolved refs: PDF exists, still useful
        print(f"[{time.strftime('%H:%M:%S')}] built in {dt:.1f}s "
              f"(LyX exit {proc.returncode}: warnings, check refs/citations)")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] BUILD FAILED (LyX exit {proc.returncode}); "
              "keeping previous PDF")
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
        print("\n".join("    " + l for l in tail))
    return ok


def open_viewer(pdf, viewer):
    try:
        if viewer:
            subprocess.Popen(viewer.split() + [str(pdf)])
        elif sys.platform == "darwin":
            app = "Skim" if Path("/Applications/Skim.app").exists() else None
            subprocess.Popen(["open"] + (["-a", app] if app else []) + [str(pdf)])
        elif sys.platform.startswith("win"):
            os.startfile(str(pdf))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(pdf)])
    except Exception as e:  # viewer problems must not kill the watcher
        print(f"could not open viewer ({e}); open {pdf} manually")


def main():
    ap = argparse.ArgumentParser(description="Auto-rebuild a LyX document to PDF on change.")
    ap.add_argument("file", type=Path, help="the .lyx file to watch")
    ap.add_argument("-o", "--output", type=Path,
                    help="output PDF (default: a temp dir, project stays clean)")
    ap.add_argument("-w", "--watch", type=Path, action="append", default=[],
                    help="extra file to watch (repeatable); the .bib next to the .lyx is added automatically")
    ap.add_argument("-f", "--format", default="pdf2",
                    help="LyX export format (pdf2=pdflatex, pdf4=xelatex, pdf5=lualatex; default pdf2)")
    ap.add_argument("-i", "--interval", type=float, default=0.5, help="poll interval in seconds")
    ap.add_argument("--settle", type=float, default=0.4,
                    help="wait until the file is quiet this long before building")
    ap.add_argument("--viewer", help='viewer command, e.g. "zathura" (default: system viewer)')
    ap.add_argument("--no-open", action="store_true", help="do not open a viewer")
    ap.add_argument("--lyx", help="path to the lyx executable")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # show progress immediately, even when piped

    src = args.file.resolve()
    if not src.is_file():
        sys.exit(f"error: {src} not found")
    lyx = find_lyx(args.lyx)

    if args.output:
        pdf = args.output.resolve()
        pdf.parent.mkdir(parents=True, exist_ok=True)
    else:
        pdf = Path(tempfile.mkdtemp(prefix="lyx-live-")) / (src.stem + ".pdf")

    extra = [p.resolve() for p in args.watch]
    watched = watch_list(src, extra)
    print(f"watching: {len(watched)} files ({', '.join(p.name for p in watched)})")
    print(f"pdf:      {pdf}")
    print("Ctrl-C to stop.\n")

    last = stamp(watched)  # snapshot BEFORE building so edits made during a build are not missed
    build(lyx, src, pdf, args.format)
    if pdf.exists() and not args.no_open:
        open_viewer(pdf, args.viewer)

    try:
        while True:
            time.sleep(args.interval)
            watched = watch_list(src, extra)  # pick up newly added includes
            cur = stamp(watched)
            if cur == last:
                continue
            # debounce: editors/scripts often write in several steps
            while True:
                time.sleep(args.settle)
                nxt = stamp(watch_list(src, extra))
                if nxt == cur:
                    break
                cur = nxt
            last = cur  # edits made while building change the stamp again and trigger another build
            build(lyx, src, pdf, args.format)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
