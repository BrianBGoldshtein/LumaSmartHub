#!/usr/bin/env python3
"""Qualify the dormant gateway sandbox in a disposable systemd network namespace.

Build-host root is required for systemd sandbox setup, not for the gateway.
No persistent service, real credentials, host listener, or external network.
"""
import argparse
import configparser
import errno
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid


def inside(root):
    import httpx
    import uvicorn
    from luma.api import create_app
    from luma.shortcut_gateway import create_gateway

    assert os.getuid() != 0, "Probe must run as the dynamic user"
    status = Path("/proc/self/status").read_text()
    assert "NoNewPrivs:\t1" in status
    assert "CapEff:\t0000000000000000" in status
    print(json.dumps({"probe_mounts": [(parts[4], parts[5]) for line in Path("/proc/self/mountinfo").read_text().splitlines()
                     if (parts := line.split())[4] in {"/", "/run", str(root)}]}), flush=True)
    try:
        (root / "readonly-probe").open("ab").close()
        raise AssertionError("Service can write the protected filesystem")
    except OSError as error:
        assert error.errno == errno.EROFS, error
    try:
        (root / "private" / "dummy-secret").read_bytes()
        raise AssertionError("Service can read the masked private directory")
    except PermissionError:
        pass
    try:
        list(Path("/home").iterdir())
        raise AssertionError("Service can enumerate home directories")
    except PermissionError:
        pass
    try:
        socket.socket(socket.AF_NETLINK, socket.SOCK_RAW).close()
        raise AssertionError("Service can create a forbidden address family")
    except OSError as error:
        assert error.errno in {errno.EPERM, errno.EAFNOSUPPORT}, error
    # A listening peer on a TEST-NET address exists in this isolated namespace,
    # outside our cgroup. Routing failures do NOT count as a policy pass.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.connect(("192.0.2.1", 9899))
            raise AssertionError("Non-loopback connection unexpectedly succeeded")
        except TimeoutError:
            pass  # A cgroup packet filter may silently drop the SYN.
        except OSError as error:
            assert error.errno in {errno.EPERM, errno.EACCES}, error

    with tempfile.TemporaryDirectory(prefix="luma-gateway-dummy-") as data:
        app = create_app(data_dir=data)
        # Fresh synthetic token exists only in the temporary DB/in memory.
        token = app.state.security.get_or_create_lan_token()
        servers = [uvicorn.Server(uvicorn.Config(target, host="127.0.0.1", port=port,
                    lifespan="off", loop="asyncio", access_log=False, log_level="error",
                    proxy_headers=False)) for target, port in [(app, 8742), (create_gateway(), 8743)]]
        threads = [threading.Thread(target=server.run, daemon=True) for server in servers]
        try:
            for thread in threads:
                thread.start()
            deadline = time.monotonic() + 15
            while not all(server.started for server in servers):
                assert time.monotonic() < deadline and all(t.is_alive() for t in threads), "Server startup failed"
                time.sleep(.05)
            with httpx.Client(base_url="http://127.0.0.1:8743", trust_env=False, timeout=5) as client:
                assert client.post("/command", json={"name": "good_night"}).status_code == 401
                result = client.post("/command", json={"name": "set_brightness", "value": 38},
                                     headers={"X-Luma-Token": token})
                assert result.status_code == 200
                assert result.json() == {"accepted": True, "message": "Brightness set to 38 percent."}
                assert app.state.luma.storage.load_settings().brightness == 38
                assert not app.state.luma.state.phone_connected
                assert client.get("/api/v1/settings").status_code == 404
        finally:
            for server in servers:
                server.should_exit = True
            for thread in threads:
                thread.join(timeout=5)
            assert not any(t.is_alive() for t in threads), "Server failed to stop"
    print(json.dumps({"sandbox": "passed", "dynamic_user": True, "filesystem_readonly": True,
                      "private_path_denied": True, "home_denied": True, "nonloopback_ip_denied": True,
                      "real_loopback_command_roundtrip": True, "host_network_exposed": False,
                      "physical_pi_qualified": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", type=Path)
    parser.add_argument("--venv", type=Path)
    parser.add_argument("--inside", type=Path)
    parser.add_argument("--network-namespace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        inside(args.inside)
        return
    if os.geteuid() != 0 or not args.unit or not args.venv:
        parser.error("Build-host root, --unit and --venv are required")
    if not args.network_namespace:
        subprocess.run(["unshare", "--net", sys.executable, __file__, "--unit", str(args.unit),
                        "--venv", str(args.venv), "--network-namespace"], check=True, timeout=75)
        return
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "Host network must remain untouched"
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    subprocess.run(["ip", "address", "add", "192.0.2.1/32", "dev", "lo"], check=True)
    unit = configparser.ConfigParser(interpolation=None)
    unit.optionxform = str
    unit.read(args.unit)
    venv = args.venv.resolve(strict=True)
    assert (venv / "bin/python").is_file()
    # All persistent production restrictions are reused. Only service lifecycle,
    # username, and executable locations differ; network isolation is stricter.
    skip = {"Type", "User", "WorkingDirectory", "ExecStart", "Restart", "RestartSec", "TimeoutStopSec"}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as peer, tempfile.TemporaryDirectory(prefix="luma-gateway-smoke-", dir="/run") as directory:
        peer.bind(("192.0.2.1", 9899))
        peer.listen(4)
        with socket.create_connection(("192.0.2.1", 9899), timeout=1):
            pass  # Positive control: peer is reachable outside the sandbox.
        root = Path(directory)
        root.chmod(0o755)
        (root / "venv").mkdir()
        shutil.copyfile(__file__, root / "probe.py")
        (root / "probe.py").chmod(0o644)
        (root / "readonly-probe").touch(mode=0o666)
        (root / "readonly-probe").chmod(0o666)
        (root / "private").mkdir(mode=0o755)
        (root / "private" / "dummy-secret").write_text("synthetic-only")
        (root / "private" / "dummy-secret").chmod(0o644)
        command = ["systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--service-type=exec",
                   "--unit=luma-gateway-smoke-" + uuid.uuid4().hex[:12]]
        for key, value in unit["Service"].items():
            if key in skip:
                continue
            if key == "InaccessiblePaths":
                value += " " + str(root / "private")
            command.append("--property=" + key + "=" + value)
        command += ["--property=PrivateNetwork=yes", "--property=RuntimeMaxSec=45",
                    "--property=NetworkNamespacePath=/proc/" + str(os.getpid()) + "/ns/net",
                    "--property=TimeoutStopSec=5", "--property=BindReadOnlyPaths=" + str(venv) + ":" + str(root / "venv"),
                    "/usr/bin/env", str(root / "venv/bin/python"), str(root / "probe.py"), "--inside", str(root)]
        subprocess.run(command, check=True, timeout=60)


if __name__ == "__main__":
    main()
