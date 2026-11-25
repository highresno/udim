"""UDIM Tiler – start appen.

  python app/main.py              åpner vinduet
  python app/main.py --selftest   eksporterer et testbilde i alle formater og avslutter (brukes i CI)
"""
from __future__ import annotations

import os
import sys


def resource(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def selftest() -> int:
    import tempfile

    import numpy as np
    import OpenImageIO as oiio

    import udim_core as core
    from api import make_preview

    tmp = tempfile.mkdtemp(prefix="udim_selftest_")
    # Blender's automatic UDIM detection expects the tile number after a dot.
    default_settings = core.ExportSettings(name="T", out_root=os.path.join(tmp, "out"))
    assert core.file_name(default_settings, 1001, 4320, 4320) == "T_4320x4320.1001.png"
    legacy_settings = core.ExportSettings(name="T", out_root=os.path.join(tmp, "out"), separator="_")
    assert core.file_name(legacy_settings, 1001, 4320, 4320) == "T_4320x4320_1001.png"
    img = np.zeros((301, 517, 4), np.float32)
    img[..., 0] = np.linspace(0, 1, 517)[None]
    img[..., 1] = np.linspace(0, 1, 301)[:, None]
    img[..., 3] = 1
    src_path = os.path.join(tmp, "src.png")
    oiio.ImageBuf(img).write(src_path, "uint8")
    src = core.load_image(src_path)
    assert src.channels == 4, src.channels
    assert make_preview(src).startswith("data:image/png;base64,")
    combos = [("PNG", "BW", "16", "zip"), ("PNG", "RGBA", "8", "zip"), ("EXR", "RGB", "half", "dwaa"),
              ("EXR", "RGBA", "float", "piz"), ("EXR", "BW", "half", "zip"), ("JPG", "RGB", "8", "zip")]
    n = 0
    for fmt, ch, depth, codec in combos:
        s = core.ExportSettings(name="T", out_root=os.path.join(tmp, "out"), tiles_x=3, tiles_y=2, scales=[1, 4],
                                fmt=fmt, channels=ch, bit_depth=depth, exr_codec=codec)
        est = core.estimate_sizes(src, s)
        assert all(sum(v) > 0 for v in est.values()), est
        for folder in core.export(src, s):
            n += len(os.listdir(folder))
    print(f"selftest ok: {n} filer i {tmp}")
    return 0 if n == len(combos) * 2 * 6 else 1


def main() -> int:
    if "--selftest" in sys.argv:
        # Vindusappen har ingen konsoll; skriv logg til fil hvis stdout mangler
        if sys.stdout is None:
            log = os.environ.get("UDIM_SELFTEST_LOG") or os.devnull
            sys.stdout = sys.stderr = open(log, "w", encoding="utf-8")
        try:
            return selftest()
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return 1
        finally:
            sys.stdout.flush()

    import webview
    from webview.dom import DOMEventHandler

    from api import Api
    from build_info import VERSION

    api = Api(startup_paths=[a for a in sys.argv[1:] if not a.startswith("-")])
    window = webview.create_window(
        f"UDIM Tiler {VERSION}", url=resource("ui", "index.html"), js_api=api,
        width=1440, height=900, min_size=(1180, 680), background_color="#eef0f4",
    )
    api.attach(window)

    def on_drop(e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if paths:
            api.push_dropped(paths)

    def on_loaded():
        try:
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception as e:  # noqa: BLE001
            print("Drag and drop not available:", e)

    loaded_once = []

    def on_loaded_once():
        if not loaded_once:
            loaded_once.append(1)
            on_loaded()

    window.events.loaded += on_loaded_once
    webview.start(private_mode=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
