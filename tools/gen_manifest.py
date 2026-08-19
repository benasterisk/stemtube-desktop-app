#!/usr/bin/env python3
"""
Generate the auto-updater manifest from a git diff between two commits.

The manifest is NEVER hand-maintained: this script derives everything from git.
Run it from inside the repo working tree.

    python tools/gen_manifest.py <base_commit> <target_commit> [--out update/manifest.json]

What it produces (see core/updater.py for the consuming contract):
  - edition            : read from edition.py at the target commit
  - min_engine_version : the updater-engine contract version this manifest needs
  - base_commit/target_commit
  - files[]            : name-status diff (A/M/D/R), each with the RAW-BYTES
                         sha256 (git show <target>:<path> | sha256, NOT the git
                         blob id) and a raw.githubusercontent URL keyed by the
                         target commit
  - pip_installs[]     : pure-Python deps ADDED between base and target, computed
                         from the diff of update/deps.json (never from shell)
  - restart_required   : true if any .py/core/routes/templates/external touched,
                         or if pip_installs is non-empty

Only files under the app's runtime tree are patchable; build-only paths are
excluded (see EXCLUDE_PREFIXES).
"""

import argparse
import hashlib
import json
import subprocess
import sys

# Repo → raw URL base. Filled from `git remote get-url origin` if not overridden.
RAW_BASE_FALLBACK = {
    "standard": "https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app",
    "friend":   "https://raw.githubusercontent.com/benasterisk/stemtube-desktop-friend",
}

MIN_ENGINE_VERSION = 1

# Paths that must NEVER be hot-patched (build-only, native, or the AppImage/Tauri
# shell). A change to any of these means a full release, not an update.
EXCLUDE_PREFIXES = (
    ".github/", "src-tauri/", "linux-installer/", "external/BTC-ISMIR19/assets",
    "dist/", "build/", "tools/", "update/",
)
EXCLUDE_EXACT = (
    "install.sh", "setup_desktop.py", "setup_dependencies.py", "build_windows.py",
    "build_tauri.py", "nuitka_build.py", "installer.iss", "installer_tauri.iss",
    "stemtube-backend.spec", "stemtube-linux-launcher.sh",
    "package.json", "package-lock.json",
)

# Documentation and repo metadata: never read at run time, so shipping them
# would cost testers bandwidth and muddy the update diff for no effect.
EXCLUDE_SUFFIXES = (".md", ".txt", ".gitignore", ".gitattributes")

# A touched file forces a restart if it is executable-imported code.
RESTART_PREFIXES = ("core/", "routes/", "external/", "templates/")
RESTART_EXACT = ("app.py", "launcher.py", "extensions.py", "edition.py", "mobile_routes.py")


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def git_bytes(*args):
    return subprocess.check_output(["git", *args])


def repo_raw_base(edition):
    try:
        url = git("remote", "get-url", "origin")
        # normalize git@github.com:owner/repo.git  or https://github.com/owner/repo.git
        url = url.replace("git@github.com:", "https://github.com/")
        if url.endswith(".git"):
            url = url[:-4]
        return url.replace("github.com", "raw.githubusercontent.com")
    except Exception:
        return RAW_BASE_FALLBACK.get(edition, RAW_BASE_FALLBACK["standard"])


def edition_at(commit):
    try:
        content = git("show", f"{commit}:edition.py")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("EDITION") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "standard"


def is_excluded(path):
    if path.endswith(EXCLUDE_SUFFIXES):
        return True
    if path in EXCLUDE_EXACT:
        return True
    return any(path.startswith(p) for p in EXCLUDE_PREFIXES)


def forces_restart(path):
    if path in RESTART_EXACT:
        return True
    if path.endswith(".py"):
        return True
    return any(path.startswith(p) for p in RESTART_PREFIXES)


def sha256_at(commit, path):
    return hashlib.sha256(git_bytes("show", f"{commit}:{path}")).hexdigest()


def deps_at(commit):
    """Return the set of pure pip deps declared in update/deps.json at a commit."""
    try:
        data = json.loads(git("show", f"{commit}:update/deps.json"))
        return set(data.get("pip_pure", []))
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_commit")
    ap.add_argument("target_commit")
    ap.add_argument("--out", default="update/manifest.json")
    args = ap.parse_args()

    base = git("rev-parse", "--short", args.base_commit)
    target = git("rev-parse", "--short", args.target_commit)
    edition = edition_at(args.target_commit)
    raw_base = repo_raw_base(edition)

    # name-status diff: e.g. "M\tstatic/js/poc/audio.js"
    diff = git("diff", "--name-status", args.base_commit, args.target_commit)
    files = []
    any_restart = False
    for line in diff.splitlines():
        parts = line.split("\t")
        code = parts[0]
        status = code[0]  # A/M/D/R/C…
        # rename lines: "R100\told\tnew" → take the new path
        path = parts[-1]
        if is_excluded(path):
            continue
        entry = {"path": path, "status": status}
        if status != "D":
            entry["sha256"] = sha256_at(args.target_commit, path)
            entry["url"] = f"{raw_base}/{target}/{path}"
        files.append(entry)
        if forces_restart(path):
            any_restart = True

    # new pure pip deps between base and target
    added_deps = sorted(deps_at(args.target_commit) - deps_at(args.base_commit))

    manifest = {
        "edition": edition,
        "min_engine_version": MIN_ENGINE_VERSION,
        "base_commit": base,
        "target_commit": target,
        "restart_required": bool(any_restart or added_deps),
        "files": files,
        "pip_installs": added_deps,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"Wrote {args.out}: {len(files)} file(s), {len(added_deps)} new dep(s), "
          f"{base} -> {target}, restart={manifest['restart_required']}")
    if added_deps:
        print(f"  new deps: {added_deps}")
    for e in files:
        print(f"  {e['status']}  {e['path']}")


if __name__ == "__main__":
    sys.exit(main())
