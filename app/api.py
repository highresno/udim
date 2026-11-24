"""Broen mellom brukergrensesnittet (HTML/JS) og bildelogikken (Python).

Alle offentlige metoder kalles fra JavaScript som window.pywebview.api.<navn>(...).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading

import numpy as np

import udim_core as core
import updater
from build_info import COMMIT, VERSION

IMAGE_TYPES = ("Images (*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.tga;*.bmp;*.psd;*.hdr)", "All files (*.*)")
PREVIEW_MAX = 1800


def to_settings(d: dict) -> core.ExportSettings:
    return core.ExportSettings(
        name=(d.get("name") or "Navn").strip(),
        out_root=(d.get("out") or "").strip(),
        tiles_x=int(d["tx"]), tiles_y=int(d["ty"]),
        fit_mode=d.get("fit", "pad"),
        scales=[int(s) for s in d.get("scales", [1])],
        filter_name=d.get("filter", "Lanczos"),
        fmt=d.get("fmt", "PNG"),
        channels=d.get("ch", "RGB"),
        bit_depth=str(d.get("depth", "8")),
        compression=int(d.get("comp", 50)),
        exr_codec=d.get("codec", "zip"),
        source_space=d.get("space", "auto"),
        convert_color=bool(d.get("convert", True)),
        separator=d.get("sep", "_"),
    )


def make_preview(src: core.SourceImage) -> str:
    """Nedskalert 8-bit sRGB PNG som data-URL til visningen."""
    import OpenImageIO as oiio
    px = src.pixels
    k = min(1.0, PREVIEW_MAX / max(src.width, src.height))
    w, h = max(1, round(src.width * k)), max(1, round(src.height * k))
    px = core.resize(px, w, h, "Box" if k < 0.5 else "Bilinear")
    mode = "RGBA" if src.channels in (2, 4) else "RGB"
    px = core.convert_channels(px, mode)
    if src.is_linear:
        px = px.copy()
        px[:, :, :3] = core.linear_to_srgb(px[:, :, :3])
    px = np.clip(px, 0, 1)
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        spec = oiio.ImageSpec(w, h, px.shape[2], oiio.UINT8)
        out = oiio.ImageOutput.create(tmp)
        out.open(tmp, spec)
        out.write_image(np.ascontiguousarray(px, dtype=np.float32))
        out.close()
        with open(tmp, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    finally:
        os.remove(tmp)


class Api:
    def __init__(self):
        self._window = None
        self._src: core.SourceImage | None = None
        self._lock = threading.Lock()

    def attach(self, window):
        self._window = window

    # ---------- hjelpere ----------
    def _js(self, fn: str, *args):
        if self._window:
            self._window.evaluate_js(f"{fn}({','.join(json.dumps(a) for a in args)})")

    # ---------- info ----------
    def info(self):
        return {"version": VERSION, "commit": COMMIT[:7], "platform": sys.platform}

    # ---------- kilde ----------
    def open_image(self):
        import webview
        res = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=IMAGE_TYPES)
        if not res:
            return None
        return self.load_path(res[0] if isinstance(res, (list, tuple)) else res)

    def load_path(self, path: str):
        try:
            with self._lock:
                self._src = core.load_image(path)
                src = self._src
            return {"ok": True, "path": path, "label": os.path.basename(path), "name": src.name,
                    "width": src.width, "height": src.height, "channels": src.channels,
                    "linear": src.is_linear, "preview": make_preview(src)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Could not open {os.path.basename(path)}: {e}"}

    def push_dropped(self, path: str):
        """Kalles fra Python når en fil slippes i vinduet."""
        self._js("window.onNativeImage", self.load_path(path))

    # ---------- utdata ----------
    def choose_folder(self, current: str = ""):
        import webview
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG, directory=current if os.path.isdir(current or "") else "")
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    def open_folder(self, path: str):
        if not os.path.isdir(path):
            return False
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True

    # ---------- eksport ----------
    def count_existing(self, settings: dict) -> int:
        if not self._src:
            return 0
        return len(core.existing_files(self._src.width, self._src.height, to_settings(settings)))

    def export(self, settings: dict):
        if not self._src:
            return {"ok": False, "error": "Import an image first."}
        s = to_settings(settings)
        if not s.out_root:
            return {"ok": False, "error": "Choose an output folder."}
        try:
            folders = core.export(self._src, s, progress=lambda d, t, m: self._js("window.onExportProgress", d, t, m))
            return {"ok": True, "folders": folders}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ---------- oppdatering ----------
    def check_update(self):
        return updater.check()

    def install_update(self, url: str):
        try:
            updater.download_and_install(url, progress=lambda p: self._js("window.onUpdateProgress", p))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        threading.Timer(0.8, self._quit).start()
        return {"ok": True}

    def _quit(self):
        if self._window:
            self._window.destroy()
