// StemTube Desktop — Tauri Shell with Splash Screen and Auto-Download
//
// Flow:
// 1. Tauri opens immediately with splash.html (small window with progress bar)
// 2. Background thread runs first_run_setup:
//    - GPU detection → selects the GPU or CPU backend archive
//    - Download backend archive (multi-part for GPU) from GitHub Releases
//    - Concatenate parts into a single zip (GPU only)
//    - Extract with tar.exe / PowerShell Expand-Archive
//    - Emits `setup_progress` events to the splash window at each step
// 3. Repair the venv if its base interpreter is missing (portable Python)
// 4. Once backend is installed, launch Python venv
// 5. Wait for Flask on 127.0.0.1:5011
// 6. Navigate the splash window to the Flask URL (main UI)

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::net::TcpStream;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

const PORT: u16 = 5011;
const STARTUP_TIMEOUT_SECS: u64 = 300;
// Win32 CREATE_NO_WINDOW flag — prevents the spawned subprocess from
// allocating or attaching to a console window. Used for the Python backend
// and helper PowerShell calls so the user only sees the Tauri WebView.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Append a line to %LOCALAPPDATA%\StemTube Desktop\tauri-shell.log.
/// Used for debugging since the release build has no console output.
fn log_shell(msg: &str) {
    let log_path = data_dir().join("tauri-shell.log");
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&log_path) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(f, "[{}] {}", now, msg);
    }
}
const MAIN_WINDOW_WIDTH: f64 = 1400.0;
const MAIN_WINDOW_HEIGHT: f64 = 900.0;

const RELEASE_BASE: &str = "https://github.com/benasterisk/stemtube-desktop-releases/releases/download/v2.0.0";
// GPU build is split into <2 GB parts (GitHub asset size limit); CPU build fits in one file.
const GPU_BACKEND_PARTS: &[&str] = &[
    "stemtube-backend-standard-gpu.zip.000",
    "stemtube-backend-standard-gpu.zip.001",
];
const CPU_BACKEND_PARTS: &[&str] = &["stemtube-backend-standard-cpu.zip"];
const GPU_COMBINED_NAME: &str = "stemtube-backend-standard-gpu.zip";
const CPU_COMBINED_NAME: &str = "stemtube-backend-standard-cpu.zip";
// Official embeddable CPython, must match the venv's major.minor (3.12).
const PYTHON_EMBED_URL: &str = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip";
const PYTHON_EMBED_VERSION: &str = "3.12.10";

struct AppState {
    backend: Mutex<Option<Child>>,
}

#[derive(Serialize, Clone)]
struct Progress {
    step: String,
    percent: f64,
    current: u64,
    total: u64,
    indeterminate: bool,
    detail: String,
}

fn emit_step(app: &AppHandle, step: &str, indeterminate: bool) {
    let _ = app.emit("setup_progress", Progress {
        step: step.to_string(),
        percent: 0.0,
        current: 0,
        total: 0,
        indeterminate,
        detail: String::new(),
    });
}

fn emit_progress(app: &AppHandle, step: &str, current: u64, total: u64) {
    let percent = if total > 0 { (current as f64 / total as f64) * 100.0 } else { 0.0 };
    let _ = app.emit("setup_progress", Progress {
        step: step.to_string(),
        percent,
        current,
        total,
        indeterminate: false,
        detail: String::new(),
    });
}

// --- Path helpers ---

fn data_dir() -> PathBuf {
    let base = std::env::var("LOCALAPPDATA")
        .unwrap_or_else(|_| std::env::var("USERPROFILE").unwrap_or_else(|_| ".".into()));
    let dir = PathBuf::from(base).join("StemTube Desktop");
    fs::create_dir_all(&dir).ok();
    dir
}

fn app_root() -> PathBuf {
    let exe = std::env::current_exe().expect("cannot resolve exe path");
    let exe_dir = exe.parent().unwrap().to_path_buf();
    if exe_dir.ends_with("target\\debug") || exe_dir.ends_with("target/debug") {
        return exe_dir.parent().and_then(|p| p.parent()).and_then(|p| p.parent()).unwrap().to_path_buf();
    }
    exe_dir
}

fn backend_dir() -> PathBuf {
    let root = app_root();
    if root.join("app.py").exists() && root.join("venv").join("Scripts").join("python.exe").exists() {
        return root;
    }
    data_dir().join("stemtube-backend-standard")
}

fn python_exe(backend: &PathBuf) -> PathBuf {
    backend.join("venv").join("Scripts").join("python.exe")
}

fn backend_exists() -> bool {
    let bd = backend_dir();
    bd.join("app.py").exists() && python_exe(&bd).exists()
}

// --- GPU detection ---

fn detect_nvidia_gpu() -> Option<String> {
    let mut cmd = Command::new("nvidia-smi");
    cmd.args(["--query-gpu=name", "--format=csv,noheader,nounits"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let output = cmd.output().ok()?;
    if output.status.success() {
        let name = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !name.is_empty() { return Some(name); }
    }
    None
}

// --- Download with progress ---
//
// Uses PowerShell in streaming mode with progress, but because we cannot easily
// parse PowerShell's progress, we poll the file size instead. First we query
// the Content-Length header, then spawn the download in the background while
// we watch the file grow.

fn download_part_with_progress(
    app: &AppHandle,
    url: &str,
    dest: &PathBuf,
    step_label: &str,
) -> Result<(), String> {
    println!("[Setup] Downloading {} → {}", url, dest.display());

    // Ensure parent dir exists
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).ok();
    }

    // Get total size with HEAD request via PowerShell
    let size_cmd = format!(
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; \
         try {{ \
            (Invoke-WebRequest -Uri '{}' -Method Head -UseBasicParsing).Headers.'Content-Length' \
         }} catch {{ '' }}",
        url
    );
    let total_bytes: u64 = {
        let mut head_cmd = Command::new("powershell");
        head_cmd.args(["-NoProfile", "-NonInteractive", "-Command", &size_cmd])
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        head_cmd.creation_flags(CREATE_NO_WINDOW);
        head_cmd.output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .and_then(|s| s.trim().parse().ok())
            .unwrap_or(0)
    };

    if total_bytes > 0 {
        println!("[Setup] Expected size: {} bytes", total_bytes);
    }

    // Start download in background PowerShell
    let dl_cmd = format!(
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; \
         $ProgressPreference = 'SilentlyContinue'; \
         Invoke-WebRequest -Uri '{}' -OutFile '{}' -UseBasicParsing",
        url,
        dest.display()
    );

    let mut dl_command = Command::new("powershell");
    dl_command.args(["-NoProfile", "-NonInteractive", "-Command", &dl_cmd])
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    dl_command.creation_flags(CREATE_NO_WINDOW);
    let mut child = dl_command.spawn()
        .map_err(|e| format!("Failed to spawn powershell: {}", e))?;

    // Poll file size for progress while download runs
    loop {
        thread::sleep(Duration::from_millis(500));

        let current = fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
        if total_bytes > 0 {
            emit_progress(app, step_label, current, total_bytes);
        } else {
            emit_step(app, &format!("{} ({} MB)", step_label, current / 1024 / 1024), true);
        }

        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    let mut stderr = String::new();
                    if let Some(mut s) = child.stderr.take() {
                        let _ = s.read_to_string(&mut stderr);
                    }
                    return Err(format!("PowerShell download failed: {}", stderr));
                }
                break;
            }
            Ok(None) => continue,
            Err(e) => return Err(format!("Download wait failed: {}", e)),
        }
    }

    if !dest.exists() || fs::metadata(dest).map(|m| m.len()).unwrap_or(0) < 1000 {
        return Err(format!("Downloaded part is empty or missing: {}", dest.display()));
    }

    // Final 100% ping
    if total_bytes > 0 {
        emit_progress(app, step_label, total_bytes, total_bytes);
    }

    Ok(())
}

fn concat_parts(parts: &[PathBuf], output: &PathBuf) -> Result<(), String> {
    println!("[Setup] Concatenating {} parts → {}", parts.len(), output.display());
    let mut out_file = fs::File::create(output)
        .map_err(|e| format!("Cannot create {}: {}", output.display(), e))?;

    for part in parts {
        let mut in_file = fs::File::open(part)
            .map_err(|e| format!("Cannot open part {}: {}", part.display(), e))?;
        std::io::copy(&mut in_file, &mut out_file)
            .map_err(|e| format!("Concat copy failed on {}: {}", part.display(), e))?;
    }

    out_file.flush().ok();
    drop(out_file);

    if !output.exists() {
        return Err("Concatenated file not found after write".into());
    }
    Ok(())
}

fn extract_zip_with_progress(
    app: &AppHandle,
    zip: &PathBuf,
    dest_dir: &PathBuf,
    step_label: &str,
) -> Result<(), String> {
    println!("[Setup] Extracting {} → {}", zip.display(), dest_dir.display());
    fs::create_dir_all(dest_dir).ok();

    let zip_size = fs::metadata(zip).map(|m| m.len()).unwrap_or(0);

    // Use bsdtar (Windows 10+ ships tar.exe in System32) — much faster than
    // PowerShell Expand-Archive for multi-GB archives. tar -xf supports zip
    // natively via libarchive.
    let tar_exe = PathBuf::from(r"C:\Windows\System32\tar.exe");
    let use_tar = tar_exe.exists();

    let mut child = if use_tar {
        println!("[Setup] Using tar.exe for fast extraction");
        let mut tar_cmd = Command::new(&tar_exe);
        tar_cmd.args(["-xf"])
            .arg(zip)
            .arg("-C")
            .arg(dest_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        tar_cmd.creation_flags(CREATE_NO_WINDOW);
        tar_cmd.spawn()
            .map_err(|e| format!("Failed to spawn tar.exe: {}", e))?
    } else {
        println!("[Setup] tar.exe not available, falling back to Expand-Archive");
        let ps_cmd = format!(
            "Expand-Archive -Path '{}' -DestinationPath '{}' -Force",
            zip.display(),
            dest_dir.display()
        );
        let mut ps_command = Command::new("powershell");
        ps_command.args(["-NoProfile", "-NonInteractive", "-Command", &ps_cmd])
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        ps_command.creation_flags(CREATE_NO_WINDOW);
        ps_command.spawn()
            .map_err(|e| format!("Failed to spawn powershell for extract: {}", e))?
    };

    // Poll destination size for progress
    // Estimated uncompressed ratio ≈ 1.85 for our zip of binaries + code
    let estimated_total = (zip_size as f64 * 1.85) as u64;

    loop {
        thread::sleep(Duration::from_millis(800));

        let current = dir_size(dest_dir);
        if estimated_total > 0 {
            let clamped = current.min(estimated_total);
            emit_progress(app, step_label, clamped, estimated_total);
        } else {
            emit_step(app, &format!("{} ({} MB)", step_label, current / 1024 / 1024), true);
        }

        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    let mut stderr = String::new();
                    if let Some(mut s) = child.stderr.take() {
                        let _ = s.read_to_string(&mut stderr);
                    }
                    return Err(format!("Extraction failed: {}", stderr));
                }
                // Final ping
                let final_size = dir_size(dest_dir);
                emit_progress(app, step_label, final_size, final_size);
                return Ok(());
            }
            Ok(None) => continue,
            Err(e) => return Err(format!("Extract wait failed: {}", e)),
        }
    }
}

fn dir_size(path: &PathBuf) -> u64 {
    let mut total = 0u64;
    if let Ok(entries) = fs::read_dir(path) {
        for entry in entries.flatten() {
            if let Ok(ft) = entry.file_type() {
                if ft.is_file() {
                    total += entry.metadata().map(|m| m.len()).unwrap_or(0);
                } else if ft.is_dir() {
                    total += dir_size(&entry.path());
                }
            }
        }
    }
    total
}

fn first_run_setup(app: AppHandle) -> Result<(), String> {
    emit_step(&app, "Detecting GPU…", true);
    let gpu = detect_nvidia_gpu();
    let (parts, combined_name): (&[&str], &str) = match gpu {
        Some(ref name) => {
            println!("[Setup] GPU detected: {}", name);
            log_shell(&format!("GPU detected ({}) → GPU backend", name));
            (GPU_BACKEND_PARTS, GPU_COMBINED_NAME)
        }
        None => {
            println!("[Setup] No NVIDIA GPU → CPU backend");
            log_shell("No NVIDIA GPU detected → CPU backend");
            (CPU_BACKEND_PARTS, CPU_COMBINED_NAME)
        }
    };

    let work_dir = data_dir().join("download");
    fs::create_dir_all(&work_dir).ok();

    // Download all parts
    let mut local_parts: Vec<PathBuf> = Vec::new();
    for (idx, part) in parts.iter().enumerate() {
        let url = format!("{}/{}", RELEASE_BASE, part);
        let dest = work_dir.join(part);
        let label = format!("Downloading part {}/{}", idx + 1, parts.len());

        // Skip if already downloaded and size > 100MB (trust previous attempts)
        let existing_size = fs::metadata(&dest).map(|m| m.len()).unwrap_or(0);
        if existing_size > 100_000_000 {
            println!("[Setup] Part {} already downloaded ({} MB)", part, existing_size / 1024 / 1024);
        } else {
            download_part_with_progress(&app, &url, &dest, &label)?;
        }
        local_parts.push(dest);
    }

    // Concatenate. The CPU build is a single file whose download dest already
    // matches `combined_name`, so only the multi-part GPU build needs a concat.
    let combined = work_dir.join(combined_name);
    if local_parts.len() > 1 {
        emit_step(&app, "Assembling archive…", true);
        concat_parts(&local_parts, &combined)?;
    }

    // Extract
    let extract_dir = data_dir().join("stemtube-backend-standard");
    fs::create_dir_all(&extract_dir).ok();
    if let Err(e) = extract_zip_with_progress(&app, &combined, &extract_dir, "Extracting backend…") {
        // Drop the downloaded archive(s): a truncated file would otherwise be
        // trusted forever by the size-based skip heuristic above, and every
        // relaunch would fail on the same corrupt zip.
        for p in &local_parts {
            fs::remove_file(p).ok();
        }
        fs::remove_file(&combined).ok();
        return Err(e);
    }

    // Cleanup
    emit_step(&app, "Cleaning up…", true);
    for p in &local_parts {
        fs::remove_file(p).ok();
    }
    fs::remove_file(&combined).ok();
    fs::remove_dir(&work_dir).ok();

    if backend_exists() {
        Ok(())
    } else {
        Err(format!(
            "Backend not found at {} after extraction",
            backend_dir().display()
        ))
    }
}

// --- Portable Python runtime & venv self-repair ---
//
// The backend archive ships the build machine's venv verbatim. A Windows venv
// is not relocatable: venv\Scripts\python.exe is a redirector stub that needs
// the base interpreter at the `home` path written in venv\pyvenv.cfg — a path
// that only exists on the build machine (exit code 103 "No Python at ..."
// everywhere else). Remedy: download the official embeddable CPython once
// into <data_dir>\python-embed, disable its ._pth file (while present it pins
// sys.path and the venv's site-packages would never load), and rewrite
// pyvenv.cfg to point at it. Checked on every startup; no-op when healthy.

fn read_pyvenv_home(backend: &PathBuf) -> Option<String> {
    let cfg_path = backend.join("venv").join("pyvenv.cfg");
    let content = fs::read_to_string(&cfg_path).ok()?;
    for line in content.lines() {
        if let Some((key, value)) = line.split_once('=') {
            if key.trim().eq_ignore_ascii_case("home") {
                return Some(value.trim().to_string());
            }
        }
    }
    None
}

/// True when the base interpreter referenced by pyvenv.cfg is missing on
/// this machine (the exit-103 symptom).
fn venv_needs_repair(backend: &PathBuf) -> bool {
    if !python_exe(backend).exists() {
        return false; // no venv at all — repair cannot help
    }
    match read_pyvenv_home(backend) {
        // python312.dll next to python.exe guards against a `home` path that
        // exists but holds a different Python version than the venv (3.12).
        Some(home) => {
            let home = PathBuf::from(&home);
            !(home.join("python.exe").exists() && home.join("python312.dll").exists())
        }
        // venv present but pyvenv.cfg missing, unreadable or home-less: the
        // stub cannot resolve a base interpreter — regenerate the cfg.
        None => true,
    }
}

/// Download + prepare the embeddable CPython under <data_dir>\python-embed.
/// Idempotent: returns immediately when python.exe is already there.
fn ensure_portable_python(app: &AppHandle) -> Result<PathBuf, String> {
    let py_dir = data_dir().join("python-embed");
    let py_exe = py_dir.join("python.exe");
    if py_exe.exists() {
        return Ok(py_dir);
    }

    log_shell("Portable Python missing, downloading embeddable runtime");
    let work_dir = data_dir().join("download");
    fs::create_dir_all(&work_dir).ok();
    let zip = work_dir.join("python-embed.zip");
    download_part_with_progress(app, PYTHON_EMBED_URL, &zip, "Downloading Python runtime…")?;

    // Extract into a temp dir first, then move into place: antivirus scanners
    // sometimes hold a transient lock on freshly written .pyd files, and a
    // half-extracted python-embed would otherwise pass the python.exe check.
    let tmp_dir = data_dir().join("python-embed.tmp");
    fs::remove_dir_all(&tmp_dir).ok();
    extract_zip_with_progress(app, &zip, &tmp_dir, "Installing Python runtime…")?;
    fs::remove_file(&zip).ok();
    fs::remove_dir(&work_dir).ok();

    // Disable the ._pth: while one exists next to python.exe, embedded Python
    // locks sys.path to the embed dir and ignores pyvenv.cfg entirely.
    // Enumerated rather than hard-coded so a future 3.13 bump cannot silently
    // leave a python313._pth active.
    let mut disabled_any = false;
    if let Ok(entries) = fs::read_dir(&tmp_dir) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with("._pth") {
                fs::rename(entry.path(), tmp_dir.join(format!("{}.disabled", name)))
                    .map_err(|e| format!("Cannot disable {}: {}", name, e))?;
                disabled_any = true;
            }
        }
    }
    if !disabled_any {
        return Err(format!(
            "No ._pth file found in {} — unexpected Python runtime layout",
            tmp_dir.display()
        ));
    }

    if !tmp_dir.join("python.exe").exists() {
        return Err(format!("python.exe not found in {} after extraction", tmp_dir.display()));
    }
    fs::remove_dir_all(&py_dir).ok();
    fs::rename(&tmp_dir, &py_dir)
        .map_err(|e| format!("Cannot move Python runtime into place: {}", e))?;

    log_shell(&format!("Portable Python ready at {}", py_dir.display()));
    Ok(py_dir)
}

/// Rewrite venv\pyvenv.cfg so home/executable point at the portable runtime.
/// No-op when the configured base interpreter still exists.
fn repair_venv_if_needed(app: &AppHandle, backend: &PathBuf) -> Result<(), String> {
    if !venv_needs_repair(backend) {
        return Ok(());
    }
    let old_home = read_pyvenv_home(backend).unwrap_or_default();
    log_shell(&format!("venv base python missing (home = {}), repairing", old_home));
    emit_step(app, "Repairing Python runtime…", true);

    let py_dir = ensure_portable_python(app)?;

    let cfg_path = backend.join("venv").join("pyvenv.cfg");
    // A missing or unreadable cfg is regenerated from scratch below.
    let content = fs::read_to_string(&cfg_path).unwrap_or_default();

    let mut seen_home = false;
    let mut seen_executable = false;
    let mut seen_version = false;
    let mut new_lines: Vec<String> = Vec::new();
    for line in content.lines() {
        if let Some((key, _)) = line.split_once('=') {
            match key.trim().to_ascii_lowercase().as_str() {
                "home" => {
                    new_lines.push(format!("home = {}", py_dir.display()));
                    seen_home = true;
                    continue;
                }
                "executable" => {
                    new_lines.push(format!("executable = {}", py_dir.join("python.exe").display()));
                    seen_executable = true;
                    continue;
                }
                "version" => {
                    // Keep the cfg consistent with the runtime we installed.
                    new_lines.push(format!("version = {}", PYTHON_EMBED_VERSION));
                    seen_version = true;
                    continue;
                }
                "command" => continue, // stale build-machine venv command, drop it
                _ => {}
            }
        }
        new_lines.push(line.to_string());
    }
    if content.trim().is_empty() {
        new_lines.push("include-system-site-packages = false".to_string());
    }
    if !seen_home {
        new_lines.push(format!("home = {}", py_dir.display()));
    }
    if !seen_version {
        new_lines.push(format!("version = {}", PYTHON_EMBED_VERSION));
    }
    if !seen_executable {
        new_lines.push(format!("executable = {}", py_dir.join("python.exe").display()));
    }
    fs::write(&cfg_path, new_lines.join("\r\n") + "\r\n")
        .map_err(|e| format!("Cannot rewrite {}: {}", cfg_path.display(), e))?;

    log_shell(&format!("pyvenv.cfg repaired → home = {}", py_dir.display()));
    Ok(())
}

// --- Backend launch ---

fn start_backend(backend: &PathBuf) -> Result<Child, String> {
    let py = python_exe(backend);
    println!("[Tauri] Backend root: {}", backend.display());
    println!("[Tauri] Python: {}", py.display());

    let mut cmd = Command::new(&py);
    cmd.arg("app.py")
        .current_dir(backend)
        .env("PYTHONIOENCODING", "utf-8")
        .env("_STEMTUBE_GPU_CONFIGURED", "1")
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // Hide the console window on Windows so the Python backend runs silently
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    cmd.spawn()
        .map_err(|e| format!("Failed to start Python backend: {}", e))
}

fn wait_for_server(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", PORT)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(500));
    }
    false
}

fn kill_backend(state: &AppState) {
    if let Ok(mut guard) = state.backend.lock() {
        if let Some(ref mut child) = *guard {
            println!("[Tauri] Stopping backend...");
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
    }
}

// --- Setup orchestration (runs in background thread) ---

fn run_setup_flow(app: AppHandle) {
    log_shell("=== run_setup_flow START ===");
    log_shell(&format!("backend_dir = {}", backend_dir().display()));
    log_shell(&format!("backend_exists = {}", backend_exists()));

    // Step 1: download + extract if needed
    if !backend_exists() {
        log_shell("backend missing, running first_run_setup");
        if let Err(e) = first_run_setup(app.clone()) {
            log_shell(&format!("first_run_setup FAILED: {}", e));
            eprintln!("[Setup] Failed: {}", e);
            let _ = app.emit("setup_error", e);
            return;
        }
        log_shell("first_run_setup OK");
    }

    // Step 2: start backend
    log_shell("Step 2: start_backend");
    let backend = backend_dir();
    log_shell(&format!("backend = {}", backend.display()));
    log_shell(&format!("python = {}", python_exe(&backend).display()));

    // Self-heal a non-relocatable venv (build-machine pyvenv.cfg → exit 103).
    // Must run here rather than in first_run_setup: backend_exists() is true
    // on already-installed broken machines, which skip Step 1 entirely.
    if let Err(e) = repair_venv_if_needed(&app, &backend) {
        log_shell(&format!("venv repair FAILED: {}", e));
        eprintln!("[Setup] Venv repair failed: {}", e);
        let _ = app.emit("setup_error", format!("Python runtime repair failed: {}", e));
        return;
    }

    emit_step(&app, "Starting backend…", true);
    let child = match start_backend(&backend) {
        Ok(c) => {
            log_shell(&format!("start_backend OK, PID={}", c.id()));
            c
        }
        Err(e) => {
            log_shell(&format!("start_backend FAILED: {}", e));
            eprintln!("[Setup] Backend launch failed: {}", e);
            let _ = app.emit("setup_error", e);
            return;
        }
    };

    // Store child in state
    if let Some(state) = app.try_state::<AppState>() {
        if let Ok(mut guard) = state.backend.lock() {
            *guard = Some(child);
        }
    }

    // Step 3: wait for Flask to respond
    log_shell("Step 3: wait_for_server");
    emit_step(&app, "Waiting for web interface…", true);
    if !wait_for_server(Duration::from_secs(STARTUP_TIMEOUT_SECS)) {
        let msg = format!("Backend did not start within {}s", STARTUP_TIMEOUT_SECS);
        log_shell(&msg);
        // Check if backend is still alive
        if let Some(state) = app.try_state::<AppState>() {
            if let Ok(mut guard) = state.backend.lock() {
                if let Some(ref mut child) = *guard {
                    match child.try_wait() {
                        Ok(Some(status)) => log_shell(&format!("Python EXITED with {:?}", status)),
                        Ok(None) => log_shell("Python still running but server unreachable"),
                        Err(e) => log_shell(&format!("try_wait error: {}", e)),
                    }
                }
            }
        }
        eprintln!("[Setup] {}", msg);
        let _ = app.emit("setup_error", msg);
        return;
    }
    log_shell("Step 3 OK: server reachable");

    // Step 4: notify the splash that we're ready
    let _ = app.emit("setup_done", ());
    thread::sleep(Duration::from_millis(600));

    // CRITICAL: build the new main window BEFORE closing the splash.
    // Tauri 2 quits the app automatically when the last window is closed,
    // so we must have a window alive at all times during the transition.
    let url = format!("http://127.0.0.1:{}", PORT);
    let parsed_url = match url.parse::<tauri::Url>() {
        Ok(u) => WebviewUrl::External(u),
        Err(_) => WebviewUrl::External(format!("http://127.0.0.1:{}/", PORT).parse().unwrap()),
    };

    let builder = WebviewWindowBuilder::new(&app, "stemtube", parsed_url)
        .title("StemTube Desktop")
        .inner_size(MAIN_WINDOW_WIDTH, MAIN_WINDOW_HEIGHT)
        .min_inner_size(1024.0, 700.0)
        .resizable(true)
        .center();

    log_shell("Building main window");
    match builder.build() {
        Ok(_main_window) => {
            log_shell("Main window built OK, closing splash");
            // New window is alive — now we can safely close the splash.
            thread::sleep(Duration::from_millis(300));
            if let Some(splash) = app.get_webview_window("main") {
                let _ = splash.close();
            }
            log_shell("Splash closed, transition complete");
        }
        Err(e) => {
            log_shell(&format!("Main window build FAILED: {}", e));
            eprintln!("[Tauri] Failed to open main window: {}", e);
            let _ = app.emit("setup_error", format!("Failed to open main window: {}", e));
        }
    }
}

// --- Entry point ---

fn main() {
    let state = AppState { backend: Mutex::new(None) };

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(state)
        .setup(|app| {
            let handle = app.handle().clone();
            // Run setup in background thread
            thread::spawn(move || {
                run_setup_flow(handle);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let label = window.label();
                log_shell(&format!("WindowEvent::Destroyed for label '{}'", label));
                // Only kill the backend when the MAIN UI window closes, not
                // when the splash window is destroyed during the transition.
                // The splash uses label "main" (legacy), the actual UI uses "stemtube".
                if label == "stemtube" {
                    log_shell("Main UI closed → killing backend");
                    if let Some(s) = window.try_state::<AppState>() {
                        kill_backend(&s);
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("Tauri error");
}
