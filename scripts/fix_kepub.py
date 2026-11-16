#!/usr/bin/env python3
"""
Batch-repair .kepub.epub manga files for Kobo Libra Colour (and other Kobo e-readers).

Fixes the dark-grey/black blank page bug caused by `display: flex` + `<svg>` wrappers
inside Fixed-Layout EPUB3 XHTML pages by replacing them with native `<img>` markup
sized to the page's viewport (e.g. 1264x1680).
"""

import argparse
import html
import re
import sys
import tempfile
import zipfile
from pathlib import Path

VIEWPORT_RE = re.compile(
    r'<meta\s+[^>]*name=["\']viewport["\'][^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
WH_RE = re.compile(r"width\s*=\s*(\d+)\s*,\s*height\s*=\s*(\d+)", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SVG_IMG_RE = re.compile(
    r'<image\b[^>]*?(?:xlink:href|href)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
HTML_IMG_RE = re.compile(
    r'<img\b[^>]*?src\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def build_clean_xhtml(title: str, img_src: str, width: int, height: int, pad_y: int = 0) -> str:
    safe_title = html.escape(title.strip()) if title else "Page"
    safe_src = html.escape(img_src.strip(), quote=True)
    img_h = max(1, height - 2 * pad_y)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head>\n"
        f"  <title>{safe_title}</title>\n"
        f'  <meta name="viewport" content="width={width}, height={height}"/>\n'
        '  <style type="text/css">\n'
        "    @page { margin: 0; padding: 0; }\n"
        f"    html, body {{ margin: 0; padding: 0; width: {width}px; height: {height}px; background-color: #ffffff; overflow: hidden; }}\n"
        f"    img {{ display: block; width: {width}px; height: {img_h}px; margin: {pad_y}px 0; padding: 0; object-fit: contain; }}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f'  <img src="{safe_src}" alt="{safe_title}"/>\n'
        "</body>\n"
        "</html>\n"
    )


def fix_xhtml_page(
    raw_bytes: bytes, default_w: int, default_h: int, pad_y: int = 0
) -> tuple[bytes, bool]:
    text = raw_bytes.decode("utf-8", errors="replace")

    img_match = SVG_IMG_RE.search(text) or HTML_IMG_RE.search(text)
    if not img_match:
        return raw_bytes, False

    img_src = img_match.group(1)

    width, height = default_w, default_h
    vp_match = VIEWPORT_RE.search(text)
    if vp_match:
        wh_match = WH_RE.search(vp_match.group(1))
        if wh_match:
            width, height = int(wh_match.group(1)), int(wh_match.group(2))

    title_match = TITLE_RE.search(text)
    title = html.unescape(title_match.group(1)) if title_match else "Page"

    new_xhtml = build_clean_xhtml(title, img_src, width, height, pad_y=pad_y)
    return new_xhtml.encode("utf-8"), True


def fix_kepub_file(
    src_path: Path,
    dst_path: Path,
    default_w: int = 1264,
    default_h: int = 1680,
    pad_y: int = 0,
) -> int:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    fixed_pages = 0

    with tempfile.NamedTemporaryFile(
        dir=dst_path.parent, delete=False, suffix=".tmp"
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        with zipfile.ZipFile(src_path, "r") as zin, zipfile.ZipFile(
            tmp_path, "w"
        ) as zout:
            # 1. mimetype must be first and uncompressed per EPUB OCF spec
            if "mimetype" in zin.namelist():
                zout.writestr(
                    "mimetype",
                    zin.read("mimetype"),
                    compress_type=zipfile.ZIP_STORED,
                )
            else:
                zout.writestr(
                    "mimetype",
                    b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED,
                )

            for info in zin.infolist():
                if info.filename == "mimetype" or info.is_dir():
                    continue

                data = zin.read(info.filename)
                lower_name = info.filename.lower()

                if lower_name.endswith((".xhtml", ".html")) and not lower_name.endswith(
                    "nav.xhtml"
                ):
                    data, changed = fix_xhtml_page(data, default_w, default_h, pad_y=pad_y)
                    if changed:
                        fixed_pages += 1

                # Store already-compressed JPEG/PNG/WebP without recompression for speed
                compress = (
                    zipfile.ZIP_STORED
                    if lower_name.endswith((".jpg", ".jpeg", ".png", ".webp"))
                    else zipfile.ZIP_DEFLATED
                )
                zout.writestr(info.filename, data, compress_type=compress)

        tmp_path.replace(dst_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return fixed_pages


def collect_inputs(paths: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.name.lower().endswith(".kepub.epub"):
            files.append(p)
        elif p.is_dir():
            pattern = "**/*.kepub.epub" if recursive else "*.kepub.epub"
            files.extend(sorted(p.glob(pattern)))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-fix .kepub.epub manga files for Kobo Libra Colour."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input .kepub.epub file(s) or directory containing them.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for fixed files (default: ./fixed_kepub).",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input files in-place instead of writing to an output directory.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively search directories for .kepub.epub files.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1264,
        help="Fallback viewport width if missing (default: 1264).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1680,
        help="Fallback viewport height if missing (default: 1680).",
    )
    parser.add_argument(
        "--pad-y",
        type=int,
        default=0,
        help="Top/bottom breathing margin in pixels inside the viewport (default: 0).",
    )

    args = parser.parse_args()
    targets = collect_inputs(args.inputs, args.recursive)
    if not targets:
        print("Aucun fichier .kepub.epub trouvé.", file=sys.stderr)
        return 1

    out_dir = args.output_dir or Path("fixed_kepub")

    for src in targets:
        dst = src if args.in_place else (out_dir / src.name)
        pages = fix_kepub_file(src, dst, args.width, args.height, pad_y=args.pad_y)
        print(f"[OK] {src.name} -> {dst} ({pages} pages corrigées)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
