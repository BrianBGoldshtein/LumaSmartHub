#!/usr/bin/env python3
"""Exercise only Luma's firewall in disposable network namespaces, no VPN/login.

Run: sudo unshare --net python3 tailscale-firewall-smoke.py ../source/system/luma-tailscale.nft
Never run without the outer unshare. --client is an internal pipe-controlled peer.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout


def isolated():
    # The ordinary WSL host network namespace belongs to PID1.
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise RuntimeError("Refusing to change host networking: use unshare --net")


def client():
    isolated()
    print("READY", flush=True)
    if sys.stdin.readline().strip() != "CONFIGURE":
        raise RuntimeError("Missing parent handshake")
    command("ip", "link", "set", "lo", "up")
    command("ip", "addr", "add", "198.18.0.2/30", "dev", "peer")
    command("ip", "-6", "addr", "add", "fd42:1234::2/64", "dev", "peer", "nodad")
    command("ip", "link", "set", "peer", "up")
    # Real TUN is layer3 and needs no Ethernet neighbor discovery. Use static
    # neighbors in this veth test so the harness has the same property.
    command("ip", "-6", "neigh", "replace", "fd42:1234::1", "lladdr", "02:00:00:00:00:01", "nud", "permanent", "dev", "peer")
    results = {}
    for family, address in ((socket.AF_INET, "198.18.0.1"), (socket.AF_INET6, "fd42:1234::1")):
        for port in (443, 8742, 8743, 22):
            with socket.socket(family) as connection:
                connection.settimeout(.5)
                try:
                    connection.connect((address, port))
                    connected = True
                except (TimeoutError, OSError):
                    connected = False
                assert connected == (port == 443), (family, port, connected)
                results[f"{'ipv4' if family == socket.AF_INET else 'ipv6'}:{port}"] = connected
    print(json.dumps(results), flush=True)


def main():
    isolated()
    rules = Path(sys.argv[1]).resolve(strict=True)
    command("ip", "link", "set", "lo", "up")
    command("nft", "add", "table", "inet", "luma_test_unrelated")
    command("nft", "-f", str(rules))
    command("nft", "-f", str(rules))  # An idempotent reload must preserve other tables.
    assert "luma_test_unrelated" in command("nft", "list", "tables")
    command("ip", "link", "add", "luma-ts", "type", "veth", "peer", "name", "peer")
    command("ip", "link", "set", "luma-ts", "address", "02:00:00:00:00:01")
    command("ip", "link", "set", "peer", "address", "02:00:00:00:00:02")
    child = subprocess.Popen(["unshare", "--net", sys.executable, __file__, "--client"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    listeners = []
    try:
        assert child.stdout.readline().strip() == "READY"
        command("ip", "link", "set", "peer", "netns", str(child.pid))
        command("ip", "addr", "add", "198.18.0.1/30", "dev", "luma-ts")
        command("ip", "-6", "addr", "add", "fd42:1234::1/64", "dev", "luma-ts", "nodad")
        command("ip", "link", "set", "luma-ts", "up")
        command("ip", "-6", "neigh", "replace", "fd42:1234::2", "lladdr", "02:00:00:00:00:02", "nud", "permanent", "dev", "luma-ts")
        for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
            for port in (443, 8742, 8743, 22):
                listener = socket.socket(family)
                if family == socket.AF_INET6:
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind((address, port))
                listener.listen(4)
                listeners.append(listener)
        output, error = child.communicate("CONFIGURE\n", timeout=20)
        assert child.returncode == 0, error
        print(json.dumps({"isolated_network_namespaces": True, "unrelated_rules_preserved": True,
                          "reload_idempotent": True, "connections": json.loads(output),
                          "tailscale_account_used": False, "hardware_qualified": False}, indent=2))
    finally:
        for listener in listeners:
            listener.close()
        if child.poll() is None:
            child.kill()
        child.wait()


if __name__ == "__main__":
    client() if sys.argv[1:] == ["--client"] else main()
