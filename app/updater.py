"""Oppdatering fra GitHub.

Sammenligner commiten appen ble bygget fra med siste commit på main.
Hvis main har endringer og GitHub Actions har bygget en ny installer for den
commiten, lastes installeren ned og kjøres stille. Appen startes på nytt etterpå.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from build_info import COMMIT, VERSION

REPO = "highresno/udim"
API = f"https://api.github.com/repos/{REPO}"
ASSET_NAME = "UDIM-Tiler-Setup.exe"


def _get(url: str):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "UDIM-Tiler-updater",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _release_commit(rel: dict) -> str:
    # Workflowen skriver "commit: <sha>" i release-teksten
    for line in (rel.get("body") or "").splitlines():
        if line.lower().startswith("commit:"):
            return line.split(":", 1)[1].strip()
    return ""


def check() -> dict:
    """Returnerer status som UI-et viser."""
    try:
        head = _get(f"{API}/commits/main")
    except Exception as e:  # noqa: BLE001
        return {"state": "error", "message": f"Fikk ikke kontakt med GitHub: {e}"}
    main_sha = head["sha"]
    info = {"current": VERSION, "currentCommit": COMMIT[:7], "mainCommit": main_sha[:7]}

    if COMMIT == "dev":
        return {**info, "state": "dev", "message": "Utviklerversjon: oppdatering er bare tilgjengelig i installert app."}
    if main_sha == COMMIT:
        return {**info, "state": "uptodate", "message": "Du har siste versjon."}

    changes = []
    try:
        cmp = _get(f"{API}/compare/{COMMIT}...{main_sha}")
        if cmp.get("status") == "behind":
            return {**info, "state": "uptodate", "message": "Du har en nyere versjon enn main."}
        changes = [c["commit"]["message"].splitlines()[0] for c in cmp.get("commits", [])][-10:]
    except Exception:  # noqa: BLE001
        pass
    info["changes"] = changes

    try:
        rel = _get(f"{API}/releases/latest")
    except Exception:  # noqa: BLE001
        rel = None
    asset = next((a for a in (rel or {}).get("assets", []) if a["name"] == ASSET_NAME), None)
    if not rel or not asset or _release_commit(rel) != main_sha:
        return {**info, "state": "building",
                "message": "Det finnes endringer på main, men den nye installeren er ikke ferdig bygget ennå. Prøv igjen om noen minutter."}
    return {**info, "state": "available", "version": rel.get("name") or rel.get("tag_name"),
            "url": asset["browser_download_url"], "size": asset.get("size", 0),
            "message": f"Ny versjon {rel.get('name') or rel.get('tag_name')} er klar."}


def download_and_install(url: str, progress=None) -> None:
    """Laster ned installeren, starter den stille og avslutter appen."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("Automatisk installasjon fungerer bare på Windows.")
    dst = os.path.join(tempfile.gettempdir(), ASSET_NAME)
    req = urllib.request.Request(url, headers={"User-Agent": "UDIM-Tiler-updater"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    # /VERYSILENT: ingen dialoger. Installeren starter appen igjen når den er ferdig.
    subprocess.Popen([dst, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
