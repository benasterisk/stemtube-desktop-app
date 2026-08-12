# StemTube — Linux graphical installer

The Linux equivalent of the Windows `setup.exe`: a tiny (~1 MB) AppImage the
user downloads and double-clicks. It opens a GTK setup window (zenity), detects
the GPU, downloads the matching self-contained engine (CPU or NVIDIA GPU) from
the `linux-v2.0.0` release, adds StemTube to the applications menu and launches
it. **No terminal, no `sudo`, no `libfuse2`** — the engine is launched with
`--appimage-extract-and-run`, which self-extracts instead of FUSE-mounting.

## Files

| File | Purpose |
|------|---------|
| `install-gui.sh` | The installer logic: GPU detection, download-with-progress, wiring, launch. Falls back to text mode if there's no display/zenity. |
| `AppRun` | AppImage entry point — sets `APPDIR`/`PATH` and runs `install-gui.sh`. |
| `stemtube-installer.desktop` / `.png` | Installer's own icon + desktop metadata. |
| `stemtube.png` | The StemTube icon copied into the user's icon theme at install time. |
| `build-installer.sh` | Builds `StemTube-Installer-x86_64.AppImage`. |

## Build

```bash
# On a Linux box / WSL2 (bundles the system zenity if present):
bash build-installer.sh
# → StemTube-Installer-x86_64.AppImage  (~1 MB)
```

Then upload it to the `linux-v2.0.0` release alongside the engine AppImages:

```bash
sha256sum StemTube-Installer-x86_64.AppImage > StemTube-Installer-x86_64.AppImage.sha256
gh release upload linux-v2.0.0 \
  StemTube-Installer-x86_64.AppImage StemTube-Installer-x86_64.AppImage.sha256 \
  --repo benasterisk/stemtube-desktop-releases --clobber
```

## Notes

- The installer is packaged with the AppImage **type2 runtime**, which
  self-extracts when FUSE is absent, so the installer itself doesn't strictly
  need `libfuse2` either.
- `install-gui.sh` handles both the single-file CPU asset and the split GPU
  asset (`.part0`/`.part1`, reassembled with `cat`, checksum-verified).
- Engine, `stemtube` command, desktop entry and icon all install under `$HOME`
  (`~/.local/share/stemtube-desktop`, `~/.local/bin`, `~/.local/share/...`) —
  no root, nothing system-wide.
