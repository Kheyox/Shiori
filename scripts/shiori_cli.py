#!/usr/bin/env python3
"""
Shiori CLI — Port Python 1:1 ultra-rapide (multi-cœurs NumPy + Pillow)
du convertisseur web Shiori (https://shiori-5be31.web.app/) pour Kobo Libra Colour (1264x1680).
"""

import argparse
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

IMG_RE = re.compile(r"\.(jpe?g|png|webp|gif|bmp|avif)$", re.IGNORECASE)


def nat_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def is_junk(name: str) -> bool:
    return (
        "__MACOSX" in name
        or name.split("/")[-1].startswith(".")
        or name.endswith("/")
    )


def parse_name(raw: str) -> dict:
    s = " " + re.sub(r"\.[a-z0-9]{2,5}$", "", str(raw), flags=re.IGNORECASE) + " "
    s = re.sub(r"[\[\(\{][^\]\)\}]*[\]\)\}]", " ", s)

    tome = None
    episode = ""

    explicit_pats = [
        re.compile(
            r"\b(?:vol(?:ume)?|v|t(?:ome)?|ch(?:ap(?:itre|ter)?)?|épisode|ep)[\s._-]*(\d{1,4})\b",
            re.IGNORECASE,
        ),
        re.compile(r"#\s*(\d{1,4})\b"),
    ]
    for pat in explicit_pats:
        m = pat.search(s)
        if m:
            tome = int(m.group(1))
            idx = m.start()
            match_len = len(m.group(0))
            before = s[:idx]
            after = s[idx + match_len :]
            s = before
            episode = after
            break

    if tome is None:
        m = re.search(r"(?:^|[\s\-_–—])0*(\d{1,3})(?:[\s\-_–—]|$)", s)
        if m:
            tome = int(m.group(1))
            idx = m.start()
            before = s[:idx]
            after = s[idx + len(m.group(0)) :]
            s = before
            episode = after

    s = re.sub(
        r"\b(cbz|zip|cbr|pdf|digital|scan|fr|vf|vostfr|kobo|kepub)\b",
        " ",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"[-–—:_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        s = re.sub(r"\.[a-z0-9]{2,5}$", "", str(raw), flags=re.IGNORECASE)
        s = re.sub(r"[\[\(\{][^\]\)\}]*[\]\)\}]", " ", s).strip()

    episode = re.sub(
        r"\b(cbz|zip|cbr|pdf|digital|scan|fr|vf|vostfr|kobo|kepub)\b",
        " ",
        episode,
        flags=re.IGNORECASE,
    )
    episode = re.sub(r"[-–—:_]+", " ", episode)
    episode = re.sub(r"\s+", " ", episode).strip()

    return {"series": s, "tome": tome, "episode": episode}


def auto_name(raw: str) -> str:
    info = parse_name(raw)
    series = re.sub(r"[._]+", " ", info["series"])
    series = re.sub(r"\s+", " ", series).strip()
    if info["tome"] is None:
        return series or raw
    return f"{series} - Tome {info['tome']:02d}"


def safe_file(n: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "_", n)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "manga"


_META_CACHE = {}


def get_series_metadata(series_name: str, comic: bool = False) -> dict | None:
    if not series_name:
        return None
    key = ("bd:" if comic else "") + series_name.strip().lower()
    if key in _META_CACHE:
        return _META_CACHE[key]

    clean = series_name.strip()
    result = None

    if not comic:
        try:
            query = """query ($search: String) {
              Media (search: $search, type: MANGA) {
                description(asHtml: false)
                staff(sort: RELEVANCE, perPage: 5) {
                  edges {
                    role
                    node { name { full } }
                  }
                }
                genres
                startDate { year }
              }
            }"""
            req = urllib.request.Request(
                "https://graphql.anilist.co",
                data=json.dumps({"query": query, "variables": {"search": clean}}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Shiori/2.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                media = (data.get("data") or {}).get("Media")
                if media:
                    edges = (media.get("staff") or {}).get("edges") or []
                    authors = [
                        e["node"]["name"]["full"]
                        for e in edges
                        if re.search(r"story|art|original", e.get("role") or "", re.I)
                    ]
                    author = ", ".join(authors) or (
                        edges[0]["node"]["name"]["full"] if edges else ""
                    )
                    desc = re.sub(r"<[^>]*>", "", media.get("description") or "")
                    desc = re.sub(r"\n{3,}", "\n\n", desc).strip()
                    year = (media.get("startDate") or {}).get("year")
                    result = {
                        "author": author,
                        "description": desc,
                        "publisher": "",
                        "publishedDate": str(year) if year else "",
                        "genres": media.get("genres") or [],
                    }
        except Exception:
            pass

    _META_CACHE[key] = result
    return result


def decide_gray(im: Image.Image, color_mode: str) -> bool:
    if color_mode == "gray":
        return True
    if color_mode == "color":
        return False
    S = 220
    s = S / max(im.width, im.height)
    w = max(1, round(im.width * s))
    h = max(1, round(im.height * s))
    small = im.resize((w, h), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.int16)
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    mask = mx > 18
    total = int(mask.sum())
    if total == 0:
        return True
    colored = int(((mx - mn > 26) & mask).sum())
    return (colored / total) < 0.035


def analyse_region(im: Image.Image, sx: int, sy: int, sw: int, sh: int, trim: bool, fill: bool) -> dict:
    crop = im.crop((sx, sy, sx + sw, sy + sh))
    samp = min(800, max(sw, sh))
    s = samp / max(sw, sh)
    w = max(2, round(sw * s))
    h = max(2, round(sh * s))
    small = crop.resize((w, h), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)  # (h, w, 3)

    P = max(2, min(6, min(w, h) // 20))
    corners = [
        arr[0:P, 0:P].mean(axis=(0, 1)),
        arr[0:P, w - P : w].mean(axis=(0, 1)),
        arr[h - P : h, 0:P].mean(axis=(0, 1)),
        arr[h - P : h, w - P : w].mean(axis=(0, 1)),
    ]
    ls = [0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for c in corners]
    agree = (max(ls) - min(ls)) < 40
    bgc = np.round(np.mean(corners, axis=0)).astype(np.int32)

    lum_arr = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    top, bottom, left, right = 0, h - 1, 0, w - 1
    if trim and agree:
        bl = 0.299 * bgc[0] + 0.587 * bgc[1] + 0.114 * bgc[2]
        thr = 52.0
        maxc = max(1, round(0.004 * max(w, h)))
        diff_lum = np.abs(lum_arr - bl) > thr
        diff_rgb = np.max(np.abs(arr - bgc.reshape(1, 1, 3)), axis=2) > 80
        is_ink = diff_lum | diff_rgb

        row_ink = is_ink.sum(axis=1)
        col_ink = is_ink.sum(axis=0)

        t, bo, l, r = 0, h - 1, 0, w - 1
        while t < bo and row_ink[t] <= maxc:
            t += 1
        while bo > t and row_ink[bo] <= maxc:
            bo -= 1
        while l < r and col_ink[l] <= maxc:
            l += 1
        while r > l and col_ink[r] <= maxc:
            r -= 1

        pad = max(2, round(0.006 * max(w, h)))
        t = max(0, t - pad)
        l = max(0, l - pad)
        bo = min(h - 1, bo + pad)
        r = min(w - 1, r + pad)
        if not ((r - l + 1) < w * 0.35 or (bo - t + 1) < h * 0.35):
            top, bottom, left, right = t, bo, l, r

    box = {
        "sx": sx + left / s,
        "sy": sy + top / s,
        "sw": min(sw, (right - left + 1) / s),
        "sh": min(sh, (bottom - top + 1) / s),
        "bg": (int(bgc[0]), int(bgc[1]), int(bgc[2])),
    }

    if fill:
        bw = right - left + 1
        bh = bottom - top + 1
        lim = 0.03
        dark = lum_arr[top : bottom + 1, left : right + 1] < 70.0
        row_line = (dark.sum(axis=1) / bw) > 0.45
        col_line = (dark.sum(axis=0) / bh) > 0.45

        mh = int(math.floor(bh * lim))
        mw = int(math.floor(bw * lim))

        kt = 0
        while kt < mh and not row_line[kt]:
            kt += 1
        kb = 0
        while kb < mh and not row_line[bh - 1 - kb]:
            kb += 1
        kl = 0
        while kl < mw and not col_line[kl]:
            kl += 1
        kr = 0
        while kr < mw and not col_line[bw - 1 - kr]:
            kr += 1

        box["safe"] = {
            "t": kt / bh,
            "b": kb / bh,
            "l": kl / bw,
            "r": kr / bw,
        }

    return box


def apply_fill(box: dict, tw: int, th: int, fill: bool, rot: int) -> dict:
    if not fill or "safe" not in box:
        return box
    ew = box["sh"] if rot else box["sw"]
    eh = box["sw"] if rot else box["sh"]
    contain = min(tw / ew, th / eh)
    vertical = (th / eh) <= (tw / ew)
    if vertical:
        sides = ["t", "b"] if rot == 0 else (["l", "r"] if rot == 1 else ["r", "l"])
    else:
        sides = ["l", "r"] if rot == 0 else (["b", "t"] if rot == 1 else ["t", "b"])

    f1 = box["safe"][sides[0]]
    f2 = box["safe"][sides[1]]
    c_max = f1 + f2
    if c_max <= 0.0005:
        return box
    sc2 = (
        min(tw / ew, th / (eh * (1.0 - c_max)))
        if vertical
        else min(th / eh, tw / (ew * (1.0 - c_max)))
    )
    if sc2 <= contain * 1.002:
        return box
    c = 1.0 - ((th / (eh * sc2)) if vertical else (tw / (ew * sc2)))
    nb = dict(box)

    def shrink(side: str, frac: float):
        src_dim = box["sh"] if side in ("t", "b") else box["sw"]
        amt = frac * src_dim
        if side == "t":
            nb["sy"] += amt
            nb["sh"] -= amt
        elif side == "b":
            nb["sh"] -= amt
        elif side == "l":
            nb["sx"] += amt
            nb["sw"] -= amt
        else:
            nb["sw"] -= amt

    shrink(sides[0], c * f1 / c_max)
    shrink(sides[1], c * f2 / c_max)
    return nb


def finish_array(arr: np.ndarray, gray: bool, sat: float, sharpen: bool) -> np.ndarray:
    # arr is uint8 (th, tw, 3)
    h, w, _ = arr.shape
    n = w * h
    f = arr.astype(np.float32)

    if gray:
        y = (f[:, :, 0] * 0.299 + f[:, :, 1] * 0.587 + f[:, :, 2] * 0.114).astype(np.int32)
        y = np.clip(y, 0, 255)
        hist = np.bincount(y.ravel(), minlength=256)
        acc = 0
        lo = 0
        for v in range(256):
            acc += hist[v]
            if acc >= n * 0.004:
                lo = v
                break
        acc = 0
        hi = 255
        for v in range(255, -1, -1):
            acc += hist[v]
            if acc >= n * 0.04:
                hi = v
                break
        lo = min(lo, 70)
        hi = max(hi, 185)
        if hi - lo > 40:
            lut = np.clip(
                np.round((np.arange(256, dtype=np.float32) - lo) / (hi - lo) * 255.0),
                0,
                255,
            ).astype(np.uint8)
            y_u8 = lut[y]
        else:
            y_u8 = y.astype(np.uint8)
        out = np.stack([y_u8, y_u8, y_u8], axis=2)
    else:
        y = f[:, :, 0] * 0.299 + f[:, :, 1] * 0.587 + f[:, :, 2] * 0.114
        y3 = y[:, :, None]
        out = np.clip(np.round(y3 + (f - y3) * sat), 0, 255).astype(np.uint8)

    if sharpen and w >= 3 and h >= 3:
        s = out.astype(np.float32)
        a = 0.4
        c = 1.0 + 4.0 * a
        center = s[1:-1, 1:-1]
        left = s[1:-1, :-2]
        right = s[1:-1, 2:]
        up = s[:-2, 1:-1]
        down = s[2:, 1:-1]
        sh_inner = np.clip(c * center - a * (left + right + up + down), 0, 255).astype(
            np.uint8
        )
        res = out.copy()
        res[1:-1, 1:-1] = sh_inner
        out = res

    return out


def compose_canvas(
    im: Image.Image,
    box0: dict,
    tw: int,
    th: int,
    fill: bool,
    bars: str,
    rot: int,
    gray: bool,
    sat: float,
    sharpen: bool,
    quality: int,
) -> bytes:
    box = apply_fill(box0, tw, th, fill, rot)
    ew = box["sh"] if rot else box["sw"]
    eh = box["sw"] if rot else box["sh"]
    sc = min(tw / ew, th / eh)

    # Anti-gonflement : si le scan source est plus petit que l'écran (sc > 1.0),
    # on conserve la résolution native avec le ratio exact 1264:1680 de la Kobo
    # (évite de doubler le poids JPEG en agrandissant du bruit de compression).
    if sc > 1.0:
        ctw = max(2, round(tw / sc))
        cth = max(2, round(th / sc))
        dw = max(1, min(ctw, round(ew)))
        dh = max(1, min(cth, round(eh)))
        do_sharpen = False  # La netteté n'est utile qu'après une réduction (sc < 1)
        eff_quality = min(quality, 78)
    else:
        ctw, cth = tw, th
        dw = max(1, round(ew * sc))
        dh = max(1, round(eh * sc))
        do_sharpen = sharpen and (sc < 0.96)
        eff_quality = quality

    x = round((ctw - dw) / 2)
    y = round((cth - dh) / 2)

    sx0 = max(0, int(round(box["sx"])))
    sy0 = max(0, int(round(box["sy"])))
    sx1 = min(im.width, max(sx0 + 1, int(round(box["sx"] + box["sw"]))))
    sy1 = min(im.height, max(sy0 + 1, int(round(box["sy"] + box["sh"]))))

    sub = im.crop((sx0, sy0, sx1, sy1))
    if rot == 1:
        sub = sub.transpose(Image.Transpose.ROTATE_270)
    elif rot == -1:
        sub = sub.transpose(Image.Transpose.ROTATE_90)

    if (sub.width, sub.height) != (dw, dh):
        resized = sub.resize((dw, dh), Image.Resampling.LANCZOS)
    else:
        resized = sub

    bg_color = (
        (255, 255, 255)
        if bars == "white"
        else ((0, 0, 0) if bars == "black" else box["bg"])
    )
    canvas = Image.new("RGB", (ctw, cth), bg_color)
    canvas.paste(resized, (x, y))

    arr = np.asarray(canvas, dtype=np.uint8)
    arr_out = finish_array(arr, gray=gray, sat=sat, sharpen=do_sharpen)

    if gray:
        final_img = Image.fromarray(arr_out[:, :, 0], mode="L")
    else:
        final_img = Image.fromarray(arr_out, mode="RGB")
    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=eff_quality, optimize=True)
    return buf.getvalue()


def process_single_page(args_tuple) -> tuple[int, list[bytes], bool, bool]:
    idx, img_bytes, cfg = args_tuple
    im = Image.open(io.BytesIO(img_bytes))
    if im.mode != "RGB":
        im = im.convert("RGB")

    gray = decide_gray(im, cfg["color"])
    sat = 1.0 if gray else cfg["sat"]
    is_spread = im.width > im.height * 1.05

    tw, th = cfg["tw"], cfg["th"]
    trim, fill, bars = cfg["trim"], cfg["fill"], cfg["bars"]
    sharpen, quality = cfg["sharpen"], cfg["quality"]
    dblmode, rotdir, rtl = cfg["spread"], cfg["rotdir"], cfg["rtl"]

    blobs = []
    if not is_spread or dblmode == "keep":
        box = analyse_region(im, 0, 0, im.width, im.height, trim, fill)
        blobs.append(
            compose_canvas(im, box, tw, th, fill, bars, 0, gray, sat, sharpen, quality)
        )
    elif dblmode == "rotate":
        box = analyse_region(im, 0, 0, im.width, im.height, trim, fill)
        rot = 1 if rotdir == "cw" else -1
        blobs.append(
            compose_canvas(im, box, tw, th, fill, bars, rot, gray, sat, sharpen, quality)
        )
    else:
        half = im.width // 2
        box_l = analyse_region(im, 0, 0, half, im.height, trim, fill)
        box_r = analyse_region(im, half, 0, im.width - half, im.height, trim, fill)
        blob_l = compose_canvas(
            im, box_l, tw, th, fill, bars, 0, gray, sat, sharpen, quality
        )
        blob_r = compose_canvas(
            im, box_r, tw, th, fill, bars, 0, gray, sat, sharpen, quality
        )
        blobs = [blob_r, blob_l] if rtl else [blob_l, blob_r]

    return idx, blobs, gray, is_spread


def generate_kepub(
    dst_path: Path,
    title: str,
    series: str,
    number: int | None,
    meta: dict | None,
    images: list[bytes],
    tw: int = 1264,
    th: int = 1680,
    rtl: bool = True,
):
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    count = len(images)
    pad = max(4, len(str(count)))
    esc = lambda s: html.escape(str(s), quote=True)

    manifest_items = [
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    ]
    spine_items = []

    with zipfile.ZipFile(dst_path, "w") as zout:
        zout.writestr(
            "mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        zout.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            compress_type=zipfile.ZIP_DEFLATED,
        )

        for i, img_bytes in enumerate(images, start=1):
            num_str = str(i).zfill(pad)
            img_name = f"page_{num_str}.jpg"
            page_id = f"page_{num_str}"
            xhtml_name = f"pages/{page_id}.xhtml"

            zout.writestr(
                f"OEBPS/images/{img_name}", img_bytes, compress_type=zipfile.ZIP_STORED
            )

            xhtml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{esc(title)} - Page {i}</title>
  <meta name="viewport" content="width={tw}, height={th}"/>
  <style type="text/css">
    @page {{ margin: 0; padding: 0; }}
    html, body {{ margin: 0; padding: 0; width: {tw}px; height: {th}px; background-color: #ffffff; overflow: hidden; }}
    img {{ display: block; width: {tw}px; height: {th}px; margin: 0; padding: 0; object-fit: contain; }}
  </style>
</head>
<body>
  <img src="../images/{img_name}" alt="Page {i}"/>
</body>
</html>"""
            zout.writestr(
                f"OEBPS/{xhtml_name}",
                xhtml_content.encode("utf-8"),
                compress_type=zipfile.ZIP_DEFLATED,
            )

            if i == 1:
                manifest_items.append(
                    f'    <item id="cover-image" href="images/{img_name}" media-type="image/jpeg" properties="cover-image"/>'
                )
            else:
                manifest_items.append(
                    f'    <item id="img_{page_id}" href="images/{img_name}" media-type="image/jpeg"/>'
                )
            manifest_items.append(
                f'    <item id="{page_id}" href="{xhtml_name}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'    <itemref idref="{page_id}"/>')

        first_page = f"pages/page_{str(1).zfill(pad)}.xhtml"
        nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
  <nav epub:type="toc" id="toc"><ol><li><a href="{first_page}">Couverture</a></li></ol></nav>
  <nav epub:type="landmarks" hidden=""><ol><li><a epub:type="cover" href="{first_page}">Couverture</a></li></ol></nav>
</body>
</html>"""
        zout.writestr(
            "OEBPS/nav.xhtml",
            nav_xhtml.encode("utf-8"),
            compress_type=zipfile.ZIP_DEFLATED,
        )

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        uid = f"urn:uuid:{uuid.uuid4()}"

        meta_lines = [
            f"    <dc:title>{esc(title)}</dc:title>",
            "    <dc:language>fr</dc:language>",
            f'    <dc:identifier id="uid">{uid}</dc:identifier>',
            f'    <meta property="dcterms:modified">{date_str}</meta>',
            '    <meta property="rendition:layout">pre-paginated</meta>',
            '    <meta property="rendition:orientation">auto</meta>',
            '    <meta property="rendition:spread">auto</meta>',
            '    <meta name="cover" content="cover-image"/>',
        ]

        if meta:
            if meta.get("author"):
                meta_lines.append(
                    f'    <dc:creator id="creator">{esc(meta["author"])}</dc:creator>'
                )
                meta_lines.append(
                    '    <meta refines="#creator" property="role" scheme="marc:relators">aut</meta>'
                )
                meta_lines.append(
                    f'    <meta name="calibre:author" content="{esc(meta["author"])}"/>'
                )
            if meta.get("description"):
                meta_lines.append(
                    f'    <dc:description>{esc(meta["description"])}</dc:description>'
                )
            if meta.get("publisher"):
                meta_lines.append(
                    f'    <dc:publisher>{esc(meta["publisher"])}</dc:publisher>'
                )
            if meta.get("publishedDate"):
                meta_lines.append(
                    f'    <dc:date>{esc(meta["publishedDate"])}</dc:date>'
                )
            for g in meta.get("genres") or []:
                meta_lines.append(f"    <dc:subject>{esc(g)}</dc:subject>")

        if series:
            meta_lines.append(
                f'    <meta property="belongs-to-collection" id="c01">{esc(series)}</meta>'
            )
            meta_lines.append(
                '    <meta refines="#c01" property="collection-type">series</meta>'
            )
            if number is not None:
                meta_lines.append(
                    f'    <meta refines="#c01" property="group-position">{number}</meta>'
                )
            meta_lines.append(
                f'    <meta name="calibre:series" content="{esc(series)}"/>'
            )
            if number is not None:
                meta_lines.append(
                    f'    <meta name="calibre:series_index" content="{number}"/>'
                )

        nl = "\n"
        opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
{nl.join(meta_lines)}
  </metadata>
  <manifest>
{nl.join(manifest_items)}
  </manifest>
  <spine page-progression-direction="{"rtl" if rtl else "ltr"}">
{nl.join(spine_items)}
  </spine>
</package>"""
        zout.writestr(
            "OEBPS/content.opf",
            opf_content.encode("utf-8"),
            compress_type=zipfile.ZIP_DEFLATED,
        )


def read_archive_pages(src_archive: Path, cfg: dict) -> list[tuple[int, bytes, dict]]:
    if zipfile.is_zipfile(src_archive):
        with zipfile.ZipFile(src_archive, "r") as zin:
            page_names = sorted(
                [
                    n
                    for n in zin.namelist()
                    if not is_junk(n) and IMG_RE.search(n)
                ],
                key=nat_key,
            )
            return [(idx, zin.read(name), cfg) for idx, name in enumerate(page_names)]

    # Fallback universel : archive RAR (même renommée .cbz) ou 7z
    import shutil, subprocess, tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="shiori_ext_"))
    try:
        res = subprocess.run(
            ["unrar", "x", "-y", "-inul", str(src_archive), f"{tmp_dir}/"],
            check=False,
        )
        if res.returncode != 0:
            subprocess.run(
                ["7z", "x", "-y", f"-o{tmp_dir}", str(src_archive)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        img_paths = sorted(
            [
                p
                for p in tmp_dir.rglob("*")
                if p.is_file()
                and not is_junk(str(p.relative_to(tmp_dir)))
                and IMG_RE.search(p.name)
            ],
            key=lambda p: nat_key(str(p.relative_to(tmp_dir))),
        )
        return [(idx, p.read_bytes(), cfg) for idx, p in enumerate(img_paths)]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def convert_volume(src_cbz: Path, out_dir: Path, workers: int = 6, series_override: str | None = None) -> Path:
    t0 = time.time()
    raw = re.sub(r"\.(cbz|zip|cbr|rar|epub)$", "", src_cbz.name, flags=re.IGNORECASE)
    parsed = parse_name(raw)
    if series_override and (
        not parsed["series"]
        or re.match(r"^(tome|vol|volume|chap|ch)\b", parsed["series"], re.IGNORECASE)
    ):
        parsed["series"] = series_override
        if parsed["tome"] is not None:
            title_base = safe_file(f"{series_override} - Tome {parsed['tome']:02d}")
        else:
            title_base = safe_file(series_override)
    else:
        title_base = safe_file(auto_name(raw))
    dst_path = out_dir / f"{title_base}.kepub.epub"

    cfg = {
        "tw": 1264,
        "th": 1680,
        "color": "auto",
        "rtl": True,
        "spread": "rotate",
        "rotdir": "cw",
        "trim": True,
        "fill": True,
        "bars": "white",
        "sharpen": True,
        "sat": 1.18,
        "quality": 82,
    }

    tasks = read_archive_pages(src_cbz, cfg)

    results = [None] * len(tasks)
    color_cnt = 0
    gray_cnt = 0
    spread_cnt = 0

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(process_single_page, t) for t in tasks]
        for f in as_completed(futs):
            idx, blobs, gray, is_spread = f.result()
            results[idx] = blobs
            if gray:
                gray_cnt += 1
            else:
                color_cnt += 1
            if is_spread:
                spread_cnt += 1

    all_images = [b for sub in results if sub for b in sub]
    meta = get_series_metadata(parsed["series"], comic=False)

    generate_kepub(
        dst_path=dst_path,
        title=title_base,
        series=parsed["series"],
        number=parsed["tome"],
        meta=meta,
        images=all_images,
        tw=1264,
        th=1680,
        rtl=True,
    )

    dt = time.time() - t0
    in_mb = src_cbz.stat().st_size / 1048576
    out_mb = dst_path.stat().st_size / 1048576
    print(
        f"[Shiori OK] {dst_path.name} ({len(all_images)} pages: {color_cnt} coul, {gray_cnt} N&B, {spread_cnt} doubles) | {in_mb:.1f} Mo -> {out_mb:.1f} Mo en {dt:.1f}s",
        flush=True,
    )
    return dst_path


def main():
    parser = argparse.ArgumentParser(description="Convertisseur Shiori CLI (Kobo Libra Colour 1264x1680)")
    parser.add_argument("input", type=Path, help="Fichier CBZ/ZIP à convertir")
    parser.add_argument("-o", "--out-dir", type=Path, required=True, help="Dossier de sortie")
    parser.add_argument("-w", "--workers", type=int, default=max(2, os.cpu_count() or 4), help="Nombre de workers")
    args = parser.parse_args()
    convert_volume(args.input, args.out_dir, workers=args.workers)


if __name__ == "__main__":
    main()
