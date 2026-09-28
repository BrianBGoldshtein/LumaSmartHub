#!/usr/bin/env python3
"""Read-only, standard-library preflight for an assembled Luma Pi.

Run as the luma user after the desktop has started. This does not qualify touch,
audio, privacy presence, campus networking, physical power loss or visual design.
No account data, settings, tokens, serial numbers or network addresses are read.
"""
import http.client
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone


def result(name, status, detail):
    return {"check": name, "status": status, "detail": detail}


def api_health():
    # Fixed loopback destination; no proxy environment, redirect, auth or state API.
    connection = http.client.HTTPConnection("127.0.0.1", 8742, timeout=5)
    try:
        connection.request("GET", "/api/v1/health", headers={"Connection": "close"})
        response = connection.getresponse()
        body = response.read(4097)
        if response.status != 200 or len(body) > 4096:
            return result("api_database", "fail", "Health endpoint failed or exceeded its size limit.")
        data = json.loads(body)
        healthy = isinstance(data, dict) and data.get("status") == "ok" and data.get("database") == "ok"
        return result("api_database", "pass" if healthy else "fail",
                      "API and database report ok." if healthy else "API/database health is not ok.")
    except (OSError, http.client.HTTPException, ValueError):
        return result("api_database", "fail", "Could not obtain a valid local health response.")
    finally:
        connection.close()


def service_state(unit, *, user=False, enabled=False):
    env = os.environ.copy()
    if user:
        # Do not trust an inherited root/admin user's bus after sudo -u luma.
        runtime = Path("/run/user") / str(os.getuid())
        if not (runtime / "bus").is_socket():
            return "unavailable"
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(runtime / "bus")
    command = ["systemctl", "--no-pager"]
    if user:
        command.append("--user")
    command += ["is-enabled" if enabled else "is-active", unit]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5,
                                   env=env, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    value = completed.stdout.strip()
    # Never emit arbitrary system output/errors: they may contain private paths.
    allowed = {"active", "inactive", "failed", "activating", "deactivating", "enabled",
               "enabled-runtime", "disabled", "masked", "static", "not-found"}
    if value not in allowed:
        return "unavailable"
    if value in {"active", "enabled", "enabled-runtime"} and completed.returncode != 0:
        return "unavailable"
    return value


def collect():
    checks = []
    try:
        model = Path("/proc/device-tree/model").read_text().strip("\0\n")
        correct_model = model.startswith("Raspberry Pi 4 Model B")
    except OSError:
        correct_model = False
    checks.append(result("pi4_model", "pass" if correct_model else "fail",
                         "Pi 4 Model B detected." if correct_model else "Pi 4 Model B was not detected; this host cannot qualify the appliance."))
    checks.append(result("arm64_userspace", "pass" if platform.machine() == "aarch64" else "fail",
                         "64-bit ARM required by this image."))
    try:
        correct_user = pwd.getpwuid(os.getuid()).pw_name == "luma"
    except KeyError:
        correct_user = False
    checks.append(result("operator_context", "pass" if correct_user else "fail",
                         "Running as luma." if correct_user else "Run as luma after the desktop starts; user-service checks are skipped."))

    checks.append(api_health())
    for unit in ("luma-api.service", "luma-network.socket", "bluetooth.service", "lightdm.service"):
        value = service_state(unit)
        checks.append(result(unit, "pass" if value == "active" else "fail", value))
    for unit in ("luma-device.service", "luma-kiosk.service"):
        value = service_state(unit, user=True) if correct_user else "not checked in this user context"
        checks.append(result(unit, "pass" if value == "active" else "fail" if correct_user else "skip", value))
    # These defaults apply before the still-unapproved encrypted phone transport.
    gateway_active = service_state("luma-shortcut-gateway.service")
    gateway_enabled = service_state("luma-shortcut-gateway.service", enabled=True)
    checks.append(result("gateway_opt_in_default",
                         "pass" if gateway_active == "inactive" and gateway_enabled == "disabled" else "fail",
                         f"Expected dormant gateway: state={gateway_active}, enablement={gateway_enabled}."))
    try:
        directory = Path("/var/lib/luma")
        info = directory.stat()
        private = stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == pwd.getpwnam("luma").pw_uid
        checks.append(result("data_directory_permissions", "pass" if private else "fail",
                             "Data directory must be luma-owned with mode 0700."))
        free_mb = shutil.disk_usage(directory).free // (1024 * 1024)
        checks.append(result("storage_headroom", "pass" if free_mb >= 1024 else "fail",
                             f"{free_mb} MiB free; preflight requires at least 1024 MiB."))
    except (OSError, KeyError):
        checks.append(result("data_directory", "fail", "Data directory could not be checked."))

    manual = [
        "Visible kiosk at native resolution; all themes, orientations and touch targets.",
        "Panel brightness, Sleep Time, touch wake and morning override.",
        "ReSpeaker microphone/speaker, echo cancellation, LEDs and Hey Luma calibration.",
        "Google consent, calendar colors, cached data and account persistence after reboot.",
        "Stanford Visitor terms or SUNet eduroam, reconnect and certificate rejection.",
        "Actual iPhone pairing, privacy arrival/departure/expiry and notification behavior.",
        "Approved encrypted phone commands, when that transport is selected and implemented.",
        "Backed-up synthetic-data physical power-cut and prolonged on-device run tests.",
    ]
    return {"checked_utc": datetime.now(timezone.utc).isoformat(),
            "automated_checks_passed": all(c["status"] == "pass" for c in checks),
            "hardware_qualified": False, "read_only": True,
            "checks": checks, "manual_gates_remaining": manual}


def main():
    report = collect()
    print(json.dumps(report, indent=2))
    return 0 if report["automated_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
