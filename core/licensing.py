"""
Hardware-bound licensing system for StemTube Desktop.

Security Model & Limitations
=============================
This is a "speed bump" licensing system designed to make casual copying
inconvenient for a low-price desktop application. It is NOT robust DRM.

How it works:
    1. A hardware fingerprint is derived from CPU, hostname, disk serial,
       and MAC address. This produces a stable, machine-specific ID.
    2. The seller generates a license key by computing HMAC-SHA256 over the
       hardware ID using a shared secret, then encoding the digest into a
       human-readable XXXXX-XXXXX-XXXXX-XXXXX format.
    3. Validation re-computes the HMAC on the local machine and compares it
       to the stored key. If the hardware changes significantly, the key
       becomes invalid.
    4. A 7-day trial is granted on first launch, tracked in an obfuscated
       `.trial` file next to the application.

Known weaknesses (acceptable for the price point):
    - The HMAC secret is compiled into the binary. A determined reverse
      engineer can extract it with a debugger or decompiler.
    - Hardware fingerprints can be spoofed by someone who understands what
      components are sampled.
    - The trial file can be deleted to reset the trial period, though the
      obfuscation makes this non-obvious to casual users.
    - On Linux/macOS, disk serial retrieval may fail, reducing fingerprint
      uniqueness (falls back to root partition UUID or hostname hash).

The goal is that a casual user who receives a copy of the binary cannot
simply run it on their own machine without obtaining their own key. This is
sufficient for honest-user licensing at a low price point.

Dependencies: Python 3.12 stdlib only (hashlib, hmac, uuid, platform,
subprocess, base64, json, time, os, struct, string, pathlib, re).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import re
import string
import struct
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Secret key — compiled into the Nuitka binary, not trivially readable.
# Replace this value before distribution. 64 hex chars = 256-bit key.
# ---------------------------------------------------------------------------
_LICENSE_SECRET: str = "FRIEND_EDITION_NO_LICENSE_PLACEHOLDER_REPLACE_BEFORE_PRO_BUILD"

# ---------------------------------------------------------------------------
# File paths (relative to this module's directory, i.e. the app directory)
# ---------------------------------------------------------------------------
_APP_DIR = Path(__file__).resolve().parent.parent  # one level up from core/
_LICENSE_FILE = _APP_DIR / ".license"
_TRIAL_FILE = _APP_DIR / ".trial"

# Trial duration
_TRIAL_DAYS: int = 7

# Character set for license key encoding (unambiguous uppercase + digits,
# no 0/O/1/I/L to avoid visual confusion)
_KEY_ALPHABET: str = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 30 chars


# ===========================================================================
# Hardware fingerprinting
# ===========================================================================

def _get_cpu_info() -> str:
    """Return a string identifying the CPU model.

    On Windows, reads from the registry via platform.processor() or WMIC.
    On Linux, parses /proc/cpuinfo. On macOS, calls sysctl.
    Falls back to platform.processor() everywhere.
    """
    system = platform.system()

    if system == "Windows":
        try:
            output = subprocess.check_output(
                ["wmic", "cpu", "get", "ProcessorId"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
            if len(lines) >= 2:
                return lines[1]
        except Exception:
            pass
        # Fallback: processor brand string
        return platform.processor() or "unknown-cpu"

    elif system == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.processor() or "unknown-cpu"

    elif system == "Darwin":
        try:
            output = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            return output.strip()
        except Exception:
            pass
        return platform.processor() or "unknown-cpu"

    return platform.processor() or "unknown-cpu"


def _get_disk_serial() -> str:
    """Return a disk serial number or volume identifier.

    On Windows, uses WMIC to query the boot drive serial.
    On Linux, reads /etc/machine-id or falls back to root partition UUID.
    On macOS, reads the IOPlatformSerialNumber via ioreg.
    """
    system = platform.system()

    if system == "Windows":
        # Try WMIC for physical disk serial
        try:
            output = subprocess.check_output(
                ["wmic", "diskdrive", "get", "SerialNumber"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
            if len(lines) >= 2 and lines[1]:
                return lines[1]
        except Exception:
            pass
        # Fallback: volume serial of C:
        try:
            output = subprocess.check_output(
                ["vol", "C:"],
                stderr=subprocess.DEVNULL,
                text=True,
                shell=True,
                timeout=5,
            )
            match = re.search(r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", output)
            if match:
                return match.group(0)
        except Exception:
            pass

    elif system == "Linux":
        # machine-id is stable across reboots, generated at install time
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, "r") as f:
                    mid = f.read().strip()
                    if mid:
                        return mid
            except Exception:
                pass

    elif system == "Darwin":
        try:
            output = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            match = re.search(r'"IOPlatformSerialNumber"\s*=\s*"(\S+)"', output)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Final fallback: hash the hostname so the fingerprint still varies
    return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


def _get_mac_address() -> str:
    """Return the MAC address of the primary network interface.

    Uses uuid.getnode() which is cross-platform. The result is formatted
    as a standard colon-separated MAC string.
    """
    mac_int = uuid.getnode()
    mac_hex = f"{mac_int:012x}"
    return ":".join(mac_hex[i:i + 2] for i in range(0, 12, 2))


def get_hardware_id() -> str:
    """Generate a stable, machine-specific hardware fingerprint.

    Combines CPU info, hostname, disk serial, and MAC address into a
    single SHA-256 hex digest. This value is what the customer sends to
    the seller to receive a license key.

    Returns:
        A 64-character lowercase hex string uniquely identifying this machine.
    """
    components = [
        _get_cpu_info(),
        platform.node(),        # hostname
        _get_disk_serial(),
        _get_mac_address(),
    ]
    raw = "|".join(components)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ===========================================================================
# License key encoding / decoding
# ===========================================================================

def _bytes_to_key_string(data: bytes, length: int = 20) -> str:
    """Encode raw bytes into the XXXXX-XXXXX-XXXXX-XXXXX key format.

    Uses a base-30 alphabet (unambiguous chars) to produce exactly
    `length` characters, then inserts dashes every 5 characters.

    Args:
        data: The raw bytes to encode (at least 16 bytes expected).
        length: Number of output characters before dashes (default 20).

    Returns:
        A formatted license key string like "A2B3C-D4E5F-G6H7J-K8M9N".
    """
    # Interpret the first 16 bytes as a 128-bit integer
    num = int.from_bytes(data[:16], byteorder="big")
    base = len(_KEY_ALPHABET)

    chars: list[str] = []
    for _ in range(length):
        num, remainder = divmod(num, base)
        chars.append(_KEY_ALPHABET[remainder])

    # Reverse so most-significant digit is first
    chars.reverse()
    key_str = "".join(chars)

    # Insert dashes every 5 characters
    groups = [key_str[i:i + 5] for i in range(0, length, 5)]
    return "-".join(groups)


def _key_string_to_num(key: str) -> int:
    """Decode a formatted license key back into its integer representation.

    Args:
        key: A license key string (dashes are stripped automatically).

    Returns:
        The integer value encoded in the key.

    Raises:
        ValueError: If the key contains invalid characters.
    """
    clean = key.replace("-", "").upper().strip()
    base = len(_KEY_ALPHABET)
    num = 0
    for ch in clean:
        idx = _KEY_ALPHABET.find(ch)
        if idx < 0:
            raise ValueError(f"Invalid character in license key: {ch!r}")
        num = num * base + idx
    return num


# ===========================================================================
# License generation (seller-side)
# ===========================================================================

def generate_license_key(hardware_id: str, secret: str | None = None) -> str:
    """Generate a license key for a given hardware fingerprint.

    This function is meant to run on the seller's machine or server.
    The customer provides their hardware_id (from get_hardware_id()),
    and this function returns the key they enter into the application.

    Args:
        hardware_id: The customer's hardware fingerprint (64 hex chars).
        secret: The HMAC secret. Defaults to the compiled-in constant.

    Returns:
        A license key in XXXXX-XXXXX-XXXXX-XXXXX format.
    """
    if secret is None:
        secret = _LICENSE_SECRET

    mac = hmac.new(
        secret.encode("utf-8"),
        hardware_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return _bytes_to_key_string(mac, length=20)


# ===========================================================================
# License validation (client-side)
# ===========================================================================

def validate_license(license_key: str) -> bool:
    """Check whether a license key is valid for this machine.

    Re-computes the expected key from the local hardware fingerprint
    and the compiled-in secret, then compares it to the provided key.
    Uses constant-time comparison to prevent timing attacks (academic
    concern here, but costs nothing).

    Args:
        license_key: The key to validate (XXXXX-XXXXX-XXXXX-XXXXX).

    Returns:
        True if the key matches this machine's fingerprint.
    """
    try:
        hw_id = get_hardware_id()
        expected = generate_license_key(hw_id)
        # Normalize both keys for comparison
        return hmac.compare_digest(
            license_key.replace("-", "").upper().strip(),
            expected.replace("-", "").upper().strip(),
        )
    except Exception:
        return False


def save_license(license_key: str) -> bool:
    """Validate and persist a license key to the .license file.

    Args:
        license_key: The key to save.

    Returns:
        True if the key is valid and was saved successfully.
    """
    if not validate_license(license_key):
        return False

    data = {
        "key": license_key.strip(),
        "hardware_id": get_hardware_id(),
        "activated_at": time.time(),
    }
    try:
        _LICENSE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def load_license() -> dict[str, Any] | None:
    """Read the stored license from disk.

    Returns:
        The license data dict, or None if no valid file exists.
    """
    try:
        if not _LICENSE_FILE.is_file():
            return None
        data = json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "key" in data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


# ===========================================================================
# Trial mode
# ===========================================================================

def _obfuscate_trial_data(data: dict[str, Any]) -> str:
    """Lightly obfuscate trial data so casual users cannot easily edit it.

    Uses base64 encoding with a simple XOR mask. This is NOT secure crypto;
    it just prevents someone from opening the file in Notepad and changing
    the date. A determined user can still reverse it.

    Args:
        data: The trial data dict to obfuscate.

    Returns:
        An obfuscated string to write to disk.
    """
    raw = json.dumps(data).encode("utf-8")
    # XOR with a repeating key
    mask = b"StemTubeDesktop2025"
    masked = bytes(b ^ mask[i % len(mask)] for i, b in enumerate(raw))
    return base64.b64encode(masked).decode("ascii")


def _deobfuscate_trial_data(blob: str) -> dict[str, Any] | None:
    """Reverse the obfuscation applied by _obfuscate_trial_data.

    Args:
        blob: The obfuscated string read from disk.

    Returns:
        The original trial data dict, or None on failure.
    """
    try:
        masked = base64.b64decode(blob.strip())
        mask = b"StemTubeDesktop2025"
        raw = bytes(b ^ mask[i % len(mask)] for i, b in enumerate(masked))
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _get_trial_data() -> dict[str, Any] | None:
    """Read trial data from the .trial file.

    Returns:
        Trial data dict with at least 'start_time', or None.
    """
    try:
        if not _TRIAL_FILE.is_file():
            return None
        blob = _TRIAL_FILE.read_text(encoding="utf-8")
        return _deobfuscate_trial_data(blob)
    except OSError:
        return None


def _init_trial() -> dict[str, Any]:
    """Create the trial file and return its data.

    Called on first launch when no license and no trial file exist.

    Returns:
        A dict with 'start_time' (Unix timestamp) and 'hardware_id'.
    """
    data = {
        "start_time": time.time(),
        "hardware_id": get_hardware_id(),
    }
    try:
        blob = _obfuscate_trial_data(data)
        _TRIAL_FILE.write_text(blob, encoding="utf-8")
    except OSError:
        pass  # If we can't write, trial just won't persist
    return data


def get_trial_days_remaining() -> float:
    """Return the number of trial days remaining (can be negative).

    If no trial file exists, initializes one (first launch).

    Returns:
        Days remaining as a float. Negative means the trial has expired.
    """
    trial = _get_trial_data()
    if trial is None:
        trial = _init_trial()

    start = trial.get("start_time", time.time())
    elapsed_seconds = time.time() - start
    elapsed_days = elapsed_seconds / 86400.0
    return _TRIAL_DAYS - elapsed_days


def is_trial_active() -> bool:
    """Check whether the trial period is still valid.

    Returns:
        True if within the 7-day trial window.
    """
    return get_trial_days_remaining() > 0


# ===========================================================================
# High-level convenience functions
# ===========================================================================

def is_licensed() -> bool:
    """Check whether the application is licensed on this machine.

    Reads the stored .license file and validates the key against the
    current hardware fingerprint.

    Returns:
        True if a valid license is installed for this hardware.
    """
    stored = load_license()
    if stored is None:
        return False
    return validate_license(stored["key"])


def is_authorized() -> bool:
    """Check whether the user may use the application.

    Returns True if either a valid license is installed OR the trial
    period has not yet expired.

    Returns:
        True if the app should allow full functionality.
    """
    return is_licensed() or is_trial_active()


def get_license_status() -> dict[str, Any]:
    """Return a comprehensive dict describing the current license state.

    This is useful for display in a settings/about dialog.

    Returns:
        A dict with the following keys:
            - status: "licensed", "trial", or "expired"
            - hardware_id: this machine's fingerprint
            - is_licensed: bool
            - is_trial: bool
            - trial_days_remaining: float (always present, may be negative)
            - license_key: str or None
            - activated_at: float (Unix timestamp) or None
    """
    hw_id = get_hardware_id()
    licensed = is_licensed()
    trial_remaining = get_trial_days_remaining()
    trial_active = trial_remaining > 0

    stored = load_license()
    license_key = stored["key"] if stored else None
    activated_at = stored.get("activated_at") if stored else None

    if licensed:
        status = "licensed"
    elif trial_active:
        status = "trial"
    else:
        status = "expired"

    return {
        "status": status,
        "hardware_id": hw_id,
        "is_licensed": licensed,
        "is_trial": trial_active and not licensed,
        "trial_days_remaining": round(trial_remaining, 2),
        "license_key": license_key,
        "activated_at": activated_at,
    }


# ===========================================================================
# CLI entry point (for testing / seller-side key generation)
# ===========================================================================

if __name__ == "__main__":
    import sys

    def _print_help() -> None:
        print("StemTube Desktop Licensing Utility")
        print()
        print("Usage:")
        print("  python licensing.py hwid              Show this machine's hardware ID")
        print("  python licensing.py generate <hwid>   Generate a license key for a hardware ID")
        print("  python licensing.py activate <key>    Activate a license key on this machine")
        print("  python licensing.py status            Show current license status")
        print("  python licensing.py validate <key>    Check if a key is valid for this machine")

    if len(sys.argv) < 2:
        _print_help()
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "hwid":
        hw = get_hardware_id()
        print(f"Hardware ID: {hw}")

    elif command == "generate":
        if len(sys.argv) < 3:
            print("Error: provide a hardware ID.")
            print("  python licensing.py generate <hardware_id>")
            sys.exit(1)
        target_hwid = sys.argv[2]
        key = generate_license_key(target_hwid)
        print(f"License key: {key}")

    elif command == "activate":
        if len(sys.argv) < 3:
            print("Error: provide a license key.")
            print("  python licensing.py activate <license_key>")
            sys.exit(1)
        key = sys.argv[2]
        if save_license(key):
            print("License activated successfully.")
        else:
            print("Invalid license key for this machine.")
            sys.exit(1)

    elif command == "status":
        info = get_license_status()
        print(f"Status:              {info['status']}")
        print(f"Hardware ID:         {info['hardware_id']}")
        print(f"Licensed:            {info['is_licensed']}")
        print(f"Trial active:        {info['is_trial']}")
        print(f"Trial days left:     {info['trial_days_remaining']}")
        if info["license_key"]:
            print(f"License key:         {info['license_key']}")
        if info["activated_at"]:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(info["activated_at"], tz=timezone.utc)
            print(f"Activated at:        {dt.isoformat()}")

    elif command == "validate":
        if len(sys.argv) < 3:
            print("Error: provide a license key.")
            sys.exit(1)
        key = sys.argv[2]
        if validate_license(key):
            print("Valid for this machine.")
        else:
            print("INVALID for this machine.")
            sys.exit(1)

    else:
        _print_help()
        sys.exit(1)
