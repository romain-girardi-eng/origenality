#!/usr/bin/env python3
"""Origenality — images without metadata: find it, strip it, prove the pixels unchanged.

An image file can carry far more than its pixels: text chunks, EXIF, XMP packets,
content-credential manifests (C2PA, in a PNG `caBX` chunk or a JPEG APP11 JUMBF
box), editor resources (JPEG APP13), comments. Those carriers name the tool and
the person behind an image, and a static site publishes them to anyone who
downloads it. The publication pass refuses an export in which any published
image carries one (`scripts/publish_export.py`), and the deployment repeats the
scan on its staged copy. This tool finds the carriers, and removes them.

What is kept is what rendering needs, and nothing else:

* PNG: IHDR, PLTE, tRNS, gAMA, cHRM, sRGB, iCCP, sBIT, pHYs, IDAT, IEND (the
  animation chunks acTL, fcTL and fdAT too). A text, time, EXIF or credential
  chunk, and any private chunk, is dropped. The pixels are then decoded before
  and after (stdlib zlib, every filter type) and compared byte for byte.
* JPEG: SOI, the frame, Huffman, quantisation, restart and scan segments, APP0
  (JFIF), APP2 when it is an ICC profile (colour depends on it) and APP14 (Adobe
  colour transform). EXIF and XMP (APP1), JUMBF/C2PA (APP11), APP13, COM and every
  other APPn are dropped. The entropy-coded data from the first SOS to EOI is
  copied unchanged, and checked identical.
* WebP: the VP8, VP8L, VP8X, ALPH, ANIM, ANMF and ICCP chunks; EXIF and XMP dropped
  (the VP8X flags are cleared accordingly).
* SVG: a `<metadata>` element or an XMP packet is reported, not rewritten.

    python3 scripts/strip_image_metadata.py --check FILE...     # exit 1 if one carries metadata
    python3 scripts/strip_image_metadata.py FILE...             # strip in place, then verify
    python3 scripts/strip_image_metadata.py --out DIR FILE...   # write stripped copies to DIR
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_KEEP = {b"IHDR", b"PLTE", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT",
            b"pHYs", b"IDAT", b"IEND", b"acTL", b"fcTL", b"fdAT"}
WEBP_KEEP = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}
# Marks that betray a metadata packet wherever it sits (an XMP packet can be
# embedded in a chunk this tool does not otherwise know).
PACKET_MARKS = re.compile(rb"<x:xmpmeta|<\?xpacket|http://ns\.adobe\.com/xap/|jumb|c2pa",
                          re.IGNORECASE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


class ImageError(ValueError):
    """A file that does not parse as the format its signature announces."""


# ---------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------

def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise ImageError("not a PNG")
    chunks, offset = [], len(PNG_SIGNATURE)
    while offset < len(data):
        if offset + 12 > len(data):
            raise ImageError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if len(body) != length:
            raise ImageError("truncated PNG chunk %r" % kind)
        chunks.append((kind, body))
        offset += 12 + length
        if kind == b"IEND":
            break
    return chunks


def png_bytes(chunks: list[tuple[bytes, bytes]]) -> bytes:
    out = bytearray(PNG_SIGNATURE)
    for kind, body in chunks:
        out += struct.pack(">I", len(body)) + kind + body
        out += struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return bytes(out)


def png_pixels(data: bytes) -> tuple[int, int, bytes]:
    """(width, height, unfiltered scanlines): the decoded image, for comparison."""
    chunks = png_chunks(data)
    header = dict(chunks).get(b"IHDR")
    if header is None:
        raise ImageError("PNG without IHDR")
    width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", header)
    raw = zlib.decompress(b"".join(body for kind, body in chunks if kind == b"IDAT"))
    if interlace:
        return width, height, raw          # compared as decompressed data
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    bpp = max(1, channels * depth // 8)
    stride = (width * channels * depth + 7) // 8
    out = bytearray()
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + left) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + up) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 0xFF
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc
                                      else up if pb <= pc else corner)) & 0xFF
        out += line
        previous = line
    return width, height, bytes(out)


def png_carriers(data: bytes) -> list[str]:
    return sorted({kind.decode("latin-1") for kind, _ in png_chunks(data)
                   if kind not in PNG_KEEP})


def strip_png(data: bytes) -> bytes:
    return png_bytes([(kind, body) for kind, body in png_chunks(data) if kind in PNG_KEEP])


# ---------------------------------------------------------------------------
# JPEG
# ---------------------------------------------------------------------------

def jpeg_segments(data: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """([(marker, whole segment bytes)], entropy-coded data from the first SOS to the end)."""
    if not data.startswith(b"\xff\xd8"):
        raise ImageError("not a JPEG")
    segments, offset = [(0xD8, data[:2])], 2
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ImageError("JPEG marker expected at byte %d" % offset)
        marker = data[offset + 1]
        if marker == 0xFF:                  # fill byte
            offset += 1
            continue
        if marker == 0xDA:                  # start of scan: the rest is image data
            return segments, data[offset:]
        if marker == 0xD9 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            segments.append((marker, data[offset:offset + 2]))
            offset += 2
            continue
        length = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        segments.append((marker, data[offset:offset + 2 + length]))
        offset += 2 + length
    raise ImageError("JPEG without a scan")


def jpeg_keeps(marker: int, segment: bytes) -> bool:
    if marker == 0xE0:
        return segment[4:9] in (b"JFIF\x00", b"JFXX\x00")
    if marker == 0xE2:
        return segment[4:16] == b"ICC_PROFILE\x00"
    if marker == 0xEE:
        return segment[4:9] == b"Adobe"
    if 0xE0 <= marker <= 0xEF or marker == 0xFE:
        return False
    return True


def jpeg_label(marker: int, segment: bytes) -> str:
    if marker == 0xFE:
        return "COM"
    name = "APP%d" % (marker - 0xE0)
    tag = segment[4:40].split(b"\x00")[0][:24].decode("latin-1", "replace").strip()
    return "%s %s" % (name, tag) if tag else name


def jpeg_carriers(data: bytes) -> list[str]:
    segments, _ = jpeg_segments(data)
    return sorted({jpeg_label(marker, segment) for marker, segment in segments
                   if not jpeg_keeps(marker, segment)})


def strip_jpeg(data: bytes) -> bytes:
    segments, scan = jpeg_segments(data)
    return b"".join(segment for marker, segment in segments if jpeg_keeps(marker, segment)) + scan


# ---------------------------------------------------------------------------
# WebP
# ---------------------------------------------------------------------------

def webp_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        raise ImageError("not a WebP")
    chunks, offset = [], 12
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        length = struct.unpack("<I", data[offset + 4:offset + 8])[0]
        chunks.append((kind, data[offset + 8:offset + 8 + length]))
        offset += 8 + length + (length & 1)
    return chunks


def webp_carriers(data: bytes) -> list[str]:
    return sorted({kind.decode("latin-1").strip() for kind, _ in webp_chunks(data)
                   if kind not in WEBP_KEEP})


def strip_webp(data: bytes) -> bytes:
    body = bytearray(b"WEBP")
    for kind, chunk in webp_chunks(data):
        if kind not in WEBP_KEEP:
            continue
        if kind == b"VP8X" and chunk:
            chunk = bytes([chunk[0] & ~0x0C]) + chunk[1:]     # EXIF and XMP flags off
        body += kind + struct.pack("<I", len(chunk)) + chunk + (b"\x00" if len(chunk) & 1 else b"")
    return b"RIFF" + struct.pack("<I", len(body)) + bytes(body)


# ---------------------------------------------------------------------------
# One file
# ---------------------------------------------------------------------------

def kind_of(data: bytes, name: str = "") -> str | None:
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if name.lower().endswith(".svg") or data.lstrip()[:5] in (b"<?xml", b"<svg "):
        return "svg"
    return None


def carriers(data: bytes, name: str = "") -> list[str]:
    """The metadata carriers of an image; [] for a clean image or a non-image."""
    kind = kind_of(data, name)
    try:
        if kind == "png":
            found = png_carriers(data)
        elif kind == "jpeg":
            found = jpeg_carriers(data)
        elif kind == "webp":
            found = webp_carriers(data)
        elif kind == "svg":
            found = ["svg <metadata>"] if re.search(rb"<metadata[\s>]", data, re.I) else []
        else:
            found = []
    except ImageError as error:
        return ["unreadable image: %s" % error]
    if kind in ("png", "jpeg", "webp", "svg") and PACKET_MARKS.search(data):
        if not found:
            found = ["metadata packet mark"]
    return found


def strip(data: bytes, name: str = "") -> bytes:
    kind = kind_of(data, name)
    if kind == "png":
        return strip_png(data)
    if kind == "jpeg":
        return strip_jpeg(data)
    if kind == "webp":
        return strip_webp(data)
    raise ImageError("cannot strip %s" % (kind or "an unknown format"))


def same_rendering(before: bytes, after: bytes, name: str = "") -> tuple[bool, str]:
    """Decoded PNG pixels, or JPEG entropy-coded data and frame, compared byte for byte."""
    kind = kind_of(before, name)
    if kind == "png":
        a, b = png_pixels(before), png_pixels(after)
        return a == b, "%dx%d, %d pixel bytes %s" % (a[0], a[1], len(a[2]),
                                                      "identical" if a == b else "DIFFER")
    if kind == "jpeg":
        (seg_a, scan_a), (seg_b, scan_b) = jpeg_segments(before), jpeg_segments(after)
        frame_a = [s for m, s in seg_a if jpeg_keeps(m, s)]
        frame_b = [s for m, s in seg_b]
        ok = scan_a == scan_b and frame_a == frame_b
        return ok, "%d bytes of entropy-coded data %s" % (len(scan_a),
                                                          "identical" if ok else "DIFFER")
    if kind == "webp":
        keep = lambda chunks: [(k, c[1:] if k == b"VP8X" else c) for k, c in chunks
                               if k in WEBP_KEEP]
        ok = keep(webp_chunks(before)) == keep(webp_chunks(after))
        return ok, "image chunks %s" % ("identical" if ok else "DIFFER")
    return False, "not compared"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="report only; exit 1 on a carrier")
    parser.add_argument("--out", type=Path, default=None, help="write stripped copies here")
    args = parser.parse_args(argv)

    dirty = failed = 0
    for path in args.files:
        data = path.read_bytes()
        found = carriers(data, path.name)
        if not found:
            print("clean      %s" % path.name)
            continue
        dirty += 1
        print("metadata   %s: %s" % (path.name, ", ".join(found)))
        if args.check:
            continue
        if kind_of(data, path.name) == "svg":
            print("   an SVG is not rewritten: remove its metadata element by hand")
            failed += 1
            continue
        stripped = strip(data, path.name)
        same, detail = same_rendering(data, stripped, path.name)
        left = carriers(stripped, path.name)
        if not same or left:
            print("   REFUSED: %s%s" % (detail, "; still carries " + ", ".join(left) if left else ""))
            failed += 1
            continue
        target = (args.out / path.name) if args.out else path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stripped)
        print("   stripped %d -> %d bytes, %s" % (len(data), len(stripped), detail))
    if args.check:
        return 1 if dirty else 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
