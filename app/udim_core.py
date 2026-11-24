"""Kjernelogikk for UDIM-tiler: lasting, oppdeling, skalering og eksport.

Ingen GUI-avhengigheter, slik at alt kan testes og brukes fra kommandolinjen.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np
import OpenImageIO as oiio

LINEAR_EXTS = {".exr", ".hdr"}

EXR_CODECS = ["zip", "zips", "piz", "dwaa", "dwab", "pxr24", "b44", "b44a", "rle", "none"]
# Codecs der komprimeringsnivå-slideren har effekt
EXR_LEVEL_CODECS = {"zip", "zips", "dwaa", "dwab"}

FILTERS = {"Lanczos": "lanczos3", "Bilinear": "triangle", "Box": "box"}
SCALES = {"1:1": 1, "1/2": 2, "1/4": 4, "1/8": 8}


# --------------------------------------------------------------------------- #
# Fargerom
# --------------------------------------------------------------------------- #
def srgb_to_linear(a: np.ndarray) -> np.ndarray:
    return np.where(a <= 0.04045, a / 12.92, ((np.clip(a, 0, None) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(a: np.ndarray) -> np.ndarray:
    a = np.clip(a, 0.0, None)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


# --------------------------------------------------------------------------- #
# Lasting
# --------------------------------------------------------------------------- #
@dataclass
class SourceImage:
    path: str
    pixels: np.ndarray  # float32, H x W x C, C = 1..4
    is_linear: bool     # gjettet ut fra filtype

    @property
    def width(self) -> int:
        return self.pixels.shape[1]

    @property
    def height(self) -> int:
        return self.pixels.shape[0]

    @property
    def channels(self) -> int:
        return self.pixels.shape[2]

    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]


def load_image(path: str) -> SourceImage:
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise IOError(f"Could not open {path}: {oiio.geterror()}")
    try:
        px = inp.read_image("float")
        if px is None:
            raise IOError(f"Could not read {path}: {inp.geterror()}")
    finally:
        inp.close()
    px = np.asarray(px, dtype=np.float32)
    if px.ndim == 2:
        px = px[:, :, None]
    if px.shape[2] > 4:
        px = px[:, :, :4]
    ext = os.path.splitext(path)[1].lower()
    return SourceImage(path, px, ext in LINEAR_EXTS)


# --------------------------------------------------------------------------- #
# Innstillinger
# --------------------------------------------------------------------------- #
@dataclass
class ExportSettings:
    name: str
    out_root: str
    tiles_x: int = 2
    tiles_y: int = 1
    fit_mode: str = "pad"            # pad | crop | stretch
    scales: list[int] = field(default_factory=lambda: [1])  # 1, 2, 4, 8 (divisor)
    filter_name: str = "Lanczos"
    fmt: str = "PNG"                 # PNG | EXR | JPG
    channels: str = "RGB"            # BW | RGB | RGBA
    bit_depth: str = "8"             # PNG: "8"/"16"; EXR: "half"/"float"
    compression: int = 50            # 0-100 (PNG/EXR), JPG: kvalitet 0-100
    exr_codec: str = "zip"
    source_space: str = "auto"       # auto | srgb | linear
    convert_color: bool = True       # sRGB->lineær for EXR, lineær->sRGB for PNG/JPG
    separator: str = "_"             # "_" -> Navn_1001.png, "." -> Navn.1001.png


def udim_number(u: int, v: int) -> int:
    """u = kolonne fra venstre, v = rad fra bunnen."""
    return 1001 + u + 10 * v


def base_tile_size(w: int, h: int, s: ExportSettings) -> tuple[int, int]:
    if s.fit_mode == "crop":
        return max(1, w // s.tiles_x), max(1, h // s.tiles_y)
    return math.ceil(w / s.tiles_x), math.ceil(h / s.tiles_y)


def tile_size(w: int, h: int, s: ExportSettings, divisor: int) -> tuple[int, int]:
    tw, th = base_tile_size(w, h, s)
    return max(1, round(tw / divisor)), max(1, round(th / divisor))


def ext_for(fmt: str) -> str:
    return {"PNG": "png", "EXR": "exr", "JPG": "jpg"}[fmt]


def describe_compression(s: ExportSettings) -> str:
    if s.fmt == "PNG":
        return f"{s.compression}%"
    if s.fmt == "JPG":
        return f"q{s.compression}"
    if s.exr_codec in EXR_LEVEL_CODECS:
        return f"{s.exr_codec}_{s.compression}%"
    return s.exr_codec


def folder_name(s: ExportSettings, tw: int, th: int) -> str:
    depth = {"8": "8bit", "16": "16bit", "half": "half", "float": "float"}[s.bit_depth]
    if s.fmt == "JPG":
        depth = "8bit"
    return f"{s.name}_{s.fmt}_{s.channels}_{depth}_{describe_compression(s)}_{tw}_{th}"


def file_name(s: ExportSettings, udim: int) -> str:
    return f"{s.name}{s.separator}{udim}.{ext_for(s.fmt)}"


def planned_outputs(src_w: int, src_h: int, s: ExportSettings) -> list[tuple[str, list[str]]]:
    """Liste av (mappe, [filer]) som eksporten vil lage."""
    out = []
    files = [file_name(s, udim_number(u, v)) for v in range(s.tiles_y) for u in range(s.tiles_x)]
    for d in s.scales:
        tw, th = tile_size(src_w, src_h, s, d)
        out.append((os.path.join(s.out_root, folder_name(s, tw, th)), files))
    return out


def existing_files(src_w: int, src_h: int, s: ExportSettings) -> list[str]:
    hits = []
    for folder, files in planned_outputs(src_w, src_h, s):
        hits += [os.path.join(folder, f) for f in files if os.path.exists(os.path.join(folder, f))]
    return hits


# --------------------------------------------------------------------------- #
# Bildebehandling
# --------------------------------------------------------------------------- #
def fit_canvas(px: np.ndarray, s: ExportSettings) -> np.ndarray:
    """Gjør bildet delelig med X/Y. UDIM 1001 er nederst til venstre, så vi
    fyller ut / beskjærer på høyre side og toppen og beholder hjørnet nede til venstre."""
    h, w, c = px.shape
    tw, th = base_tile_size(w, h, s)
    W, H = tw * s.tiles_x, th * s.tiles_y
    if s.fit_mode == "crop":
        return px[h - H:, :W]
    if s.fit_mode == "stretch":
        return resize(px, W, H, s.filter_name)
    if (W, H) == (w, h):
        return px
    canvas = np.zeros((H, W, c), dtype=np.float32)
    canvas[H - h:, :w] = px  # bilde nederst til venstre, padding øverst og til høyre
    return canvas


def resize(px: np.ndarray, w: int, h: int, filter_name: str) -> np.ndarray:
    if px.shape[1] == w and px.shape[0] == h:
        return px
    src = oiio.ImageBuf(np.ascontiguousarray(px))
    roi = oiio.ROI(0, w, 0, h, 0, 1, 0, px.shape[2])
    dst = oiio.ImageBufAlgo.resize(src, filtername=FILTERS.get(filter_name, "lanczos3"), roi=roi)
    if dst.has_error:
        raise RuntimeError(dst.geterror())
    return np.asarray(dst.get_pixels(oiio.FLOAT), dtype=np.float32).reshape(h, w, px.shape[2])


def convert_channels(px: np.ndarray, mode: str) -> np.ndarray:
    c = px.shape[2]
    if c == 1:
        rgb, a = np.repeat(px, 3, axis=2), None
    elif c == 2:
        rgb, a = np.repeat(px[:, :, :1], 3, axis=2), px[:, :, 1:2]
    else:
        rgb, a = px[:, :, :3], (px[:, :, 3:4] if c == 4 else None)
    if mode == "BW":
        return (rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[:, :, None]
    if mode == "RGB":
        return rgb
    if a is None:
        a = np.ones(rgb.shape[:2] + (1,), dtype=np.float32)
    return np.concatenate([rgb, a], axis=2)


def apply_color(px: np.ndarray, src_linear: bool, s: ExportSettings) -> np.ndarray:
    if not s.convert_color:
        return px
    want_linear = s.fmt == "EXR"
    if want_linear == src_linear:
        return px
    out = px.copy()
    n = 3 if px.shape[2] >= 3 else 1  # aldri konverter alfa
    out[:, :, :n] = srgb_to_linear(px[:, :, :n]) if want_linear else linear_to_srgb(px[:, :, :n])
    return out


def write_tile(path: str, px: np.ndarray, s: ExportSettings) -> None:
    h, w, c = px.shape
    if s.fmt == "PNG":
        fmt = oiio.UINT16 if s.bit_depth == "16" else oiio.UINT8
    elif s.fmt == "JPG":
        fmt = oiio.UINT8
    else:
        fmt = oiio.HALF if s.bit_depth == "half" else oiio.FLOAT
    spec = oiio.ImageSpec(w, h, c, fmt)
    if c == 1:
        spec.channelnames = ("Y",)
    elif c == 3:
        spec.channelnames = ("R", "G", "B")
    else:
        spec.channelnames = ("R", "G", "B", "A")
        spec.alpha_channel = 3

    if s.fmt == "PNG":
        level = round(s.compression / 100 * 9)
        spec.attribute("png:compressionLevel", level)
    elif s.fmt == "JPG":
        spec.attribute("Compression", f"jpeg:{max(1, s.compression)}")
        spec.attribute("CompressionQuality", max(1, s.compression))
    else:
        codec = s.exr_codec
        if codec in ("zip", "zips"):
            codec = f"{codec}:{max(1, round(s.compression / 100 * 9))}"
        elif codec in ("dwaa", "dwab"):
            codec = f"{codec}:{max(1, s.compression)}"
        spec.attribute("compression", codec)

    if s.fmt != "EXR":
        px = np.clip(px, 0.0, 1.0)
    out = oiio.ImageOutput.create(path)
    if out is None:
        raise IOError(oiio.geterror())
    if not out.open(path, spec):
        raise IOError(out.geterror())
    ok = out.write_image(np.ascontiguousarray(px, dtype=np.float32))
    out.close()
    if not ok:
        raise IOError(out.geterror())


def export(src: SourceImage, s: ExportSettings, progress=None, cancelled=None) -> list[str]:
    """Eksporterer alle valgte oppløsninger. progress(done, total, msg)."""
    if not 1 <= s.tiles_x <= 10:
        raise ValueError("UDIM allows 1 to 10 tiles in X.")
    if s.fmt == "JPG" and s.channels == "RGBA":
        raise ValueError("JPG does not support alpha.")

    src_linear = {"auto": src.is_linear, "srgb": False, "linear": True}[s.source_space]
    canvas = fit_canvas(src.pixels, s)
    canvas = convert_channels(canvas, s.channels)
    canvas = apply_color(canvas, src_linear, s)

    total = len(s.scales) * s.tiles_x * s.tiles_y
    done, folders = 0, []
    for d in s.scales:
        tw, th = tile_size(src.width, src.height, s, d)
        scaled = resize(canvas, tw * s.tiles_x, th * s.tiles_y, s.filter_name)
        folder = os.path.join(s.out_root, folder_name(s, tw, th))
        os.makedirs(folder, exist_ok=True)
        folders.append(folder)
        H = scaled.shape[0]
        for v in range(s.tiles_y):
            for u in range(s.tiles_x):
                if cancelled and cancelled():
                    return folders
                y1 = H - v * th          # v teller fra bunnen
                tile = scaled[y1 - th:y1, u * tw:(u + 1) * tw]
                fname = file_name(s, udim_number(u, v))
                write_tile(os.path.join(folder, fname), tile, s)
                done += 1
                if progress:
                    progress(done, total, fname)
    return folders
