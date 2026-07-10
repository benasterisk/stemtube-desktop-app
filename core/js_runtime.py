"""Deno JavaScript runtime management for yt-dlp.

yt-dlp needs a JavaScript runtime (deno preferred, node accepted) to solve
YouTube's EJS/nsig challenges. Without one, the web player client yields no
usable formats and downloads fail with "Requested format is not available".
End-user machines typically have neither runtime installed, so the backend
bundles deno.exe (like ffmpeg) and auto-downloads it as a fallback.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile

from .config import APP_DIR

DENO_DIR = os.path.join(APP_DIR, "deno")
DENO_EXECUTABLE = os.path.join(
    DENO_DIR, "deno.exe" if platform.system() == "Windows" else "deno"
)

DENO_DOWNLOAD_URL = (
    "https://github.com/denoland/deno/releases/latest/download/"
    "deno-x86_64-pc-windows-msvc.zip"
)

_download_lock = threading.Lock()


def get_deno_path():
    """Return the bundled deno executable, a PATH-resolved one, or None."""
    if os.path.exists(DENO_EXECUTABLE):
        return DENO_EXECUTABLE
    return shutil.which("deno")


def get_js_runtimes_config():
    """js_runtimes dict for yt-dlp: bundled deno first, system node fallback."""
    runtimes = {}
    deno = get_deno_path()
    runtimes["deno"] = {"path": deno} if deno else {}
    runtimes["node"] = {}
    return runtimes


def ensure_deno_available():
    """Ensure a JS runtime exists; download the bundled deno if none found.

    Cheap when deno is already bundled/on PATH or node is installed.
    Serialized by a lock so concurrent callers don't double-download.
    """
    if get_deno_path() or shutil.which("node"):
        return True
    if platform.system() != "Windows":
        print("[js_runtime] No JS runtime (deno/node) found; YouTube downloads may fail")
        return False
    with _download_lock:
        if get_deno_path():
            return True
        tmp_path = None
        try:
            print(f"[js_runtime] Downloading Deno from {DENO_DOWNLOAD_URL}...")
            os.makedirs(DENO_DIR, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp_path = tmp.name
            urllib.request.urlretrieve(DENO_DOWNLOAD_URL, tmp_path)
            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extract("deno.exe", DENO_DIR)
            result = subprocess.run(
                [DENO_EXECUTABLE, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                print(f"[js_runtime] Deno ready: {result.stdout.splitlines()[0]}")
                return True
            print(f"[js_runtime] Downloaded deno.exe failed to run: {result.stderr}")
            return False
        except Exception as e:
            print(f"[js_runtime] Error downloading Deno: {e}")
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
