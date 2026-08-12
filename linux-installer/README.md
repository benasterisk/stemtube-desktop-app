# StemTube — Linux installers

The Linux distribution mirrors the Windows model. What users install depends on
their distro:

## Ubuntu / Debian — `.deb` package (the `.exe` equivalent)

`deb/` builds **`stemtube-desktop_2.0.0_amd64.deb`** — a package the user
downloads and **double-clicks** (opens in the software centre → Install), or
installs with `sudo apt install ./stemtube-desktop_2.0.0_amd64.deb`. It adds a
**StemTube Desktop** apps-menu entry and a `stemtube` command. On the **first
launch**, `stemtube` opens a small GTK window (zenity), detects the GPU,
downloads the matching self-contained engine (CPU or NVIDIA GPU) from the
`linux-v2.0.0` release with a progress bar, then runs it. The engine is launched
with `--appimage-extract-and-run` → **no `libfuse2`, no root at run time**.

| File | Purpose |
|------|---------|
| `deb/stemtube-run.sh` | Installed as `/usr/bin/stemtube`: GPU detection, first-run engine download, launch. Falls back to text mode when headless. |
| `deb/build-deb.sh` | Builds the `.deb` (control, postinst/postrm, desktop entry, icon). |
| `deb/stemtube.png` | App icon shipped in the package. |

```bash
# On a Linux box / WSL2 (Ubuntu 22.04):
bash deb/build-deb.sh
# → stemtube-desktop_2.0.0_amd64.deb
```

`Depends: curl, zenity`. Package files are owned root:root
(`dpkg-deb --root-owner-group`); the engine and its data install per-user under
`~/.local/share/stemtube-desktop` and `~/.stemtube-desktop`.

## Other distros (Fedora, Arch, openSUSE…) — engine AppImage directly

No package manager step. Download `StemTube-x86_64-cpu.AppImage` (or the GPU
parts) from the release and run it with `--appimage-extract-and-run` (no FUSE):

```bash
chmod +x StemTube-x86_64-cpu.AppImage
./StemTube-x86_64-cpu.AppImage --appimage-extract-and-run
```

## Note — why not a double-clickable installer AppImage?

An earlier attempt shipped the *installer* itself as an AppImage. On a desktop
without `libfuse2`, double-clicking an `.AppImage` fails ("no application
installed for AppImage bundles") because the file manager can't mount it — the
`--appimage-extract-and-run` fallback only applies when launched from a shell.
The `.deb` is the format Ubuntu/Debian desktops execute natively on double-click,
so it's the real `.exe` equivalent there.

## Publishing

```bash
sha256sum stemtube-desktop_2.0.0_amd64.deb > stemtube-desktop_2.0.0_amd64.deb.sha256
gh release upload linux-v2.0.0 \
  stemtube-desktop_2.0.0_amd64.deb stemtube-desktop_2.0.0_amd64.deb.sha256 \
  --repo benasterisk/stemtube-desktop-releases --clobber
```
