"""Broen mellom brukergrensesnittet (HTML/JS) og bildelogikken (Python).

Alle offentlige metoder kalles fra JavaScript som window.pywebview.api.<navn>(...).
Hver åpne fane er et "dokument" med egen id og eget kildebilde.
"""
from __future__ import annotations

import base64
import itertools
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
PROJECT_EXT = ".udimt"
PROJECT_TYPES = ("UDIM Tiler project (*.udimt)",)
PREVIEW_MAX = 1800


def to_settings(d: dict) -> core.ExportSettings:
    return core.ExportSettings(
        name=(d.get("name") or "Name").strip(),
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


def _first(res):
    if not res:
        return None
    return res[0] if isinstance(res, (list, tuple)) else res


class Api:
    def __init__(self, startup_paths: list[str] | None = None):
        self._window = None
        self._docs: dict[str, core.SourceImage] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._est_gen: dict[str, int] = {}
        self._startup = list(startup_paths or [])

    def attach(self, window):
        self._window = window

    def _js(self, fn: str, *args):
        if self._window:
            self._window.evaluate_js(f"{fn}({','.join(json.dumps(a) for a in args)})")

    # ---------- info ----------
    def info(self):
        return {"version": VERSION, "commit": COMMIT[:7], "platform": sys.platform}

    def startup_files(self):
        """Filer appen ble startet med (dobbeltklikk på .udimt eller et bilde)."""
        paths, self._startup = self._startup, []
        return [os.path.abspath(p) for p in paths if os.path.exists(p)]

    # ---------- bilder ----------
    def choose_images(self):
        """Filvelger. Selve innlastingen skjer etterpå, så UI-et kan vise fremdrift."""
        import webview
        res = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True, file_types=IMAGE_TYPES)
        return [os.path.abspath(p) for p in (res or [])]

    def load_path(self, path: str):
        try:
            src = core.load_image(path)
            doc = f"d{next(self._ids)}"
            with self._lock:
                self._docs[doc] = src
            return {"ok": True, "doc": doc, "path": os.path.abspath(path), "label": os.path.basename(path),
                    "name": src.name, "width": src.width, "height": src.height, "channels": src.channels,
                    "fileSize": src.file_size, "pixelFormat": src.pixel_format,
                    "linear": src.is_linear, "preview": make_preview(src)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "path": path, "error": f"Could not open {os.path.basename(path)}: {e}"}

    def close_doc(self, doc: str):
        with self._lock:
            self._docs.pop(doc, None)
        return True

    def push_dropped(self, paths: list[str]):
        """Kalles fra Python når filer slippes i vinduet."""
        self._js("window.onNativeDrop", paths)

    # ---------- prosjekt ----------
    def save_project(self, data: dict, path: str | None = None, save_as: bool = False):
        import webview
        if save_as or not path:
            start = os.path.dirname(path) if path else ""
            fname = os.path.basename(path) if path else "Untitled" + PROJECT_EXT
            path = _first(self._window.create_file_dialog(webview.SAVE_DIALOG, directory=start,
                                                          save_filename=fname, file_types=PROJECT_TYPES))
            if not path:
                return None
        if not path.lower().endswith(PROJECT_EXT):
            path += PROJECT_EXT
        base = os.path.dirname(os.path.abspath(path))
        tabs = []
        for t in data.get("tabs", []):
            img = t.get("image", "")
            try:
                rel = os.path.relpath(img, base)
            except ValueError:  # annen disk på Windows
                rel = None
            tabs.append({**t, "imageRelative": rel})
        doc = {"app": "UDIM Tiler", "format": 1, "version": VERSION, "active": data.get("active", 0), "tabs": tabs}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except OSError as e:
            return {"ok": False, "error": f"Could not save project: {e}"}
        return {"ok": True, "path": path, "label": os.path.basename(path)}

    def choose_project(self):
        import webview
        return _first(self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=PROJECT_TYPES))

    def read_project(self, path: str):
        """Leser prosjektfilen og finner bildene. UI-et laster dem etterpå én for én."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Could not read project: {e}"}
        base = os.path.dirname(os.path.abspath(path))
        tabs, missing = [], []
        for t in data.get("tabs", []):
            candidates = [t.get("image", "")]
            if t.get("imageRelative"):
                candidates.insert(0, os.path.normpath(os.path.join(base, t["imageRelative"])))
            img = next((c for c in candidates if c and os.path.exists(c)), None)
            if not img:
                missing.append(t.get("image") or "?")
                continue
            tabs.append({"path": os.path.abspath(img), "settings": t.get("settings", {})})
        return {"ok": True, "path": path, "label": os.path.basename(path), "active": data.get("active", 0),
                "tabs": tabs, "missing": missing}

    # ---------- utdata ----------
    def choose_folder(self, current: str = ""):
        import webview
        return _first(self._window.create_file_dialog(webview.FOLDER_DIALOG,
                                                      directory=current if os.path.isdir(current or "") else ""))

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

    # ---------- størrelse ----------
    def estimate(self, settings: dict):
        """Anslått byte per tile. Eldre forespørsler for samme fane avbrytes."""
        doc = settings.get("doc")
        src = self._docs.get(doc)
        if not src:
            return None
        gen = self._est_gen.get(doc, 0) + 1
        self._est_gen[doc] = gen
        try:
            sizes = core.estimate_sizes(src, to_settings(settings))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if self._est_gen.get(doc) != gen:
            return None  # utdatert
        return {"ok": True, "doc": doc, "sizes": {str(k): v for k, v in sizes.items()}}

    # ---------- eksport ----------
    def count_existing(self, settings: dict) -> int:
        src = self._docs.get(settings.get("doc"))
        if not src:
            return 0
        return len(core.existing_files(src.width, src.height, to_settings(settings)))

    def export(self, settings: dict):
        src = self._docs.get(settings.get("doc"))
        if not src:
            return {"ok": False, "error": "Import an image first."}
        s = to_settings(settings)
        if not s.out_root:
            return {"ok": False, "error": "Choose an output folder."}
        try:
            folders = core.export(src, s, progress=lambda d, t, m: self._js("window.onExportProgress", d, t, m))
            sizes = {f: {x: os.path.getsize(os.path.join(f, x)) for x in os.listdir(f)} for f in folders}
            return {"ok": True, "folders": folders, "sizes": sizes}
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
