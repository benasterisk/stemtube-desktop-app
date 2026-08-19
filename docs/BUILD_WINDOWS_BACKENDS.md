# Rebuilding the Windows backend archives

How the `stemtube-backend-standard-{cpu,gpu}.zip` assets on the **v2.0.0**
release are produced. Written after the 2026-08-20 rebuild, which brought the
Windows engines back in line with `main` after seven weeks of drift.

## Why they must go on the `v2.0.0` tag

`src-tauri/src/main.rs` hard-codes `releases/download/v2.0.0`. Every installer
already in users' hands fetches its backend from that tag, so refreshed engines
**must replace the assets in place** — publishing them under a new tag would
leave existing installers downloading the old ones.

## What goes in an archive

A backend archive is just the app source plus a ready-to-run virtualenv:

```
app.py  launcher.py  extensions.py  edition.py
patch_madmom.py  check_config.py
core/  routes/  templates/  static/  external/  utils/
venv/
```

Excluded: `__pycache__/`, `*.pyc`, `logs/`, `flask_session/`, `*.db`, and any
test data. A stray `_testdata/` or `logs/` folder inflates the zip and ships
your machine's paths to users.

## Building the venv

Both variants use Python 3.12 and the **same 109 packages**; only torch differs.
The fastest honest way to get the dependency list is to freeze an existing
working install and strip the GPU-only wheels:

```bash
# from a known-good venv
python -m pip freeze > gpu-freeze.txt
```

Then drop `torch`, `torchaudio`, everything starting with `nvidia-`, and
`triton` — those have no CPU counterpart and would pull ~3 GB for nothing.

```bash
python -m venv venv
venv/Scripts/python -m pip install --upgrade pip wheel setuptools

# CPU
venv/Scripts/python -m pip install torch==2.6.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cpu

# GPU (CUDA 12.4)
venv/Scripts/python -m pip install torch==2.6.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

venv/Scripts/python -m pip install -r requirements-without-torch.txt
```

`madmom` installs from a pinned git commit, not PyPI — keep the `madmom @ git+...`
line from the freeze exactly as it is.

Sizes for reference: CPU venv ≈ 2.1 GB, GPU venv ≈ 5.1 GB.

## Verify before packaging

Never zip an untested tree. Both checks below caught real problems:

```bash
# 1. every critical import resolves
venv/Scripts/python -c "import torch, torchaudio, demucs, faster_whisper, \
    madmom, flask, librosa, soundfile, numpy, mir_eval, webview; print('ok')"

# 2. the server actually boots and serves the mixer
venv/Scripts/python app.py       # then: curl http://127.0.0.1:5011/mixer
```

For the GPU build also confirm CUDA survived the copy:

```bash
venv/Scripts/python -c "import torch; print(torch.cuda.is_available())"
```

## Packaging

```powershell
Compress-Archive -Path 'C:\path\to\build\*' `
  -DestinationPath 'stemtube-backend-standard-cpu.zip' `
  -CompressionLevel Optimal -Force
```

Compressed: CPU ≈ 547 MB, GPU ≈ 2.7 GB. The GPU zip exceeds GitHub's 2 GB
per-asset limit, so split it into 1500 MiB parts named `.000`, `.001` — the
format the installer already expects:

```python
CHUNK = 1500 * 1024 * 1024
```

Checksum the **whole** archive (not the parts), and always test that the parts
reassemble to that exact digest before uploading. A silently truncated part
produces an archive that fails only at the user's end.

## Uploading

```bash
gh release upload v2.0.0 <asset> \
  --repo benasterisk/stemtube-desktop-releases --clobber
```

Upload the GPU parts and the `.sha256`, never the 2.7 GB archive itself.

## Existing installs

Rebuilding does **not** update anyone who already installed. Those users run
`update/patcher-windows.ps1` once, which installs the in-app updater; from then
on the app patches itself from `update/manifest.json` and no rebuild is needed
for source-only fixes.
