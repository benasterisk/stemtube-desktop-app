# StemTube Desktop Friend — Status

## TL;DR

L'installer Beta tester fonctionne **end-to-end depuis zéro**, validé en test virgin (suppression complète + relance).

## Test virgin du soir (12 avril 01:17)

Suppression de tout dans `%LOCALAPPDATA%\StemTube Desktop Friend\` sauf `stemtube-desktop.exe`, relance, monitoring complet :

| Étape | Durée | Status |
|---|---|---|
| Splash window apparaît | <1s | OK |
| GPU detection | <1s | OK (RTX 4050) |
| Download chunk 1 (1.8 GB depuis GitHub) | ~2 min | OK |
| Download chunk 2 (977 MB depuis GitHub) | ~50s | OK |
| Concat parts → combined.zip (pure Rust) | ~10s | OK |
| Extract via tar.exe natif Win10+ | ~2 min | OK |
| Cleanup chunks + combined.zip | <1s | OK |
| Start Python backend (creation_flags=CREATE_NO_WINDOW) | <1s | OK |
| Wait for Flask HTTP 200 | 31s | OK |
| Build main window (1400×900 centered) | <1s | OK |
| Close splash (label "main") | <1s | OK |
| Backend reste alive après splash close | 12s+ check | OK |
| **TOTAL clic → UI ouverte** | **3 min 24s** | OK |

État final : 1× `stemtube-desktop.exe`, 2× `python.exe`, HTTP 200 stable.

## Bugs corrigés cette nuit

1. **Window hors écran après splash** — Création nouvelle window AVANT close splash (était l'inverse), au lieu de set_size sur la même window
2. **Console terminal noire** — `CREATE_NO_WINDOW` Win32 flag sur tous les subprocess (Python, PowerShell, tar.exe, nvidia-smi) côté Rust ET côté Python (`stems_extractor.py` demucs subprocess, `app.py` yt-dlp pip update)
3. **Backend killed par window event** — `on_window_event Destroyed` filtré pour ne tuer le backend que quand la window `stemtube` (UI) se ferme, pas la `main` (splash)
4. **Chord regen 500** — `mir_eval` manquant pour BTC chord detector. Installé dans dev venv + ajouté à `setup_desktop.py` + inclus dans le nouveau zip GitHub
5. **Focus Lyrics controls inactifs** (Play/Stop/Tempo/Pitch) — `initPopupControls()` n'était appelé que dans `initGridPopup()` qui n'était lui-même appelé que **après** chargement de chords. Maintenant câblé dans le `constructor` de `ChordDisplay`
6. **Config.json paths absolus du repo source** — Retiré `ffmpeg_path` et `downloads_directory` du JSON, recalculés au démarrage par `validate_and_fix_config_paths()`
7. **Détection dev/installed mode** — `core/config.py` regarde maintenant `src-tauri/Cargo.toml` au lieu de `venv/` (qui était présent dans les deux modes après extract du zip), et utilise `LOCALAPPDATA/StemTube Desktop Friend` au lieu de `LOCALAPPDATA/StemTube Desktop` (cohabitation possible avec la version Pro)

## Release v1.0.0 sur GitHub

URL : https://github.com/benasterisk/stemtube-desktop-friend-releases/releases/tag/v1.0.0

| Asset | Taille |
|---|---|
| `StemTube_Desktop_Friend_1.0.0_x64-setup.exe` | 1.4 MB |
| `stemtube-backend-friend-gpu.zip.000` | 1800 MB |
| `stemtube-backend-friend-gpu.zip.001` | 976 MB |
| **TOTAL** | **2.71 GB** |

Repo `stemtube-desktop-friend-releases` est **public** pour permettre le download via PowerShell sans auth. Le repo source `stemtube-desktop-friend` reste **privé**.

## Code source pushé sur GitHub

URL : https://github.com/benasterisk/stemtube-desktop-friend (privé)

Dernier commit : `3240b9e End-to-end installer flow fixes`

## Pour distribuer aux Beta testeurs

Donne-leur juste ce lien : https://github.com/benasterisk/stemtube-desktop-friend-releases/releases/download/v1.0.0/StemTube_Desktop_Friend_1.0.0_x64-setup.exe

L'installer NSIS (1.4 MB) installe l'exe, et le premier lancement télécharge le backend (~2.7 GB) en arrière-plan avec progression visible dans le splash.

## Reste à valider manuellement

L'app est en ce moment lancée et HTTP 200 répond sur localhost:5011. À ton réveil, vérifie dans la fenêtre Tauri :

- [ ] Library visible et vide
- [ ] Recherche YouTube fonctionne (taper "Julien Doré" par exemple)
- [ ] Download d'une chanson aboutit
- [ ] Extraction stems (htdemucs_6s) fonctionne sans console noire
- [ ] Mixer s'ouvre, chord detection BTC marche
- [ ] **Detect Beats** (madmom) regenerate fonctionne
- [ ] **Focus Lyrics** : ouvre le popup, vérifie que Play / Stop / Tempo / Pitch / Size sont tous **actifs**
- [ ] Pas de console terminal noire visible nulle part pendant tout le flow

Si quelque chose cloche, le log Tauri shell est dans `%LOCALAPPDATA%\StemTube Desktop Friend\tauri-shell.log` et les logs backend dans `%LOCALAPPDATA%\StemTube Desktop Friend\stemtube-backend-friend\logs\`.
