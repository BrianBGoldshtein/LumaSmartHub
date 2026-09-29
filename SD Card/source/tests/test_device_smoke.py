"""Host-only tests of the on-device preflight; no Pi or personal data needed."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("device_smoke", Path(__file__).with_name("device_smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeTests(unittest.TestCase):
    def test_fixed_read_only_health_request(self):
        with patch.object(smoke.http.client, "HTTPConnection") as connection:
            instance = connection.return_value
            instance.getresponse.return_value.status = 200
            instance.getresponse.return_value.read.return_value = b'{"status":"ok","database":"ok","secret":"not-for-report"}'
            report = smoke.api_health()
            self.assertEqual(report["status"], "pass")
            self.assertNotIn("not-for-report", json.dumps(report))
            connection.assert_called_once_with("127.0.0.1", 8742, timeout=5)
            instance.request.assert_called_once_with("GET", "/api/v1/health", headers={"Connection": "close"})
            instance.getresponse.return_value.read.assert_called_once_with(4097)
            instance.close.assert_called_once()

    def test_bad_or_redirected_health_fails_without_echoing_body(self):
        for status, body in [(302, b"secret"), (500, b"secret"), (200, b"secret"),
                             (200, b"x" * 4097), (200, b'[]'),
                             (200, b'{"status":"ok","database":"error"}')]:
            with self.subTest(status=status, body=body[:20]), patch.object(smoke.http.client, "HTTPConnection") as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = status, body
                report = smoke.api_health()
                self.assertEqual(report["status"], "fail")
                self.assertNotIn("secret", json.dumps(report))

    def test_offline_health_is_bounded_and_connection_closes(self):
        with patch.object(smoke.http.client, "HTTPConnection") as connection:
            connection.return_value.request.side_effect = TimeoutError("private-host-info")
            report = smoke.api_health()
            self.assertEqual(report["status"], "fail")
            self.assertNotIn("private-host-info", json.dumps(report))
            connection.return_value.close.assert_called_once()

    def test_service_queries_never_mutate_or_print_arbitrary_output(self):
        with patch.object(smoke.subprocess, "run") as run:
            run.return_value = SimpleNamespace(stdout="active\n", returncode=0)
            self.assertEqual(smoke.service_state("luma-api.service"), "active")
            self.assertEqual(run.call_args.args[0], ["systemctl", "--no-pager", "is-active", "luma-api.service"])
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
            run.return_value = SimpleNamespace(stdout="secret", returncode=0)
            self.assertEqual(smoke.service_state("luma-api.service"), "unavailable")
            run.return_value = SimpleNamespace(stdout="active", returncode=1)
            self.assertEqual(smoke.service_state("luma-api.service"), "unavailable")

    def test_user_service_selects_own_bus_not_inherited_admin_bus(self):
        with patch.object(smoke.os, "getuid", return_value=1234), patch.object(smoke.Path, "is_socket", return_value=True), \
                patch.dict(smoke.os.environ, {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/private/admin/bus"}), \
                patch.object(smoke.subprocess, "run") as run:
            run.return_value = SimpleNamespace(stdout="active", returncode=0)
            self.assertEqual(smoke.service_state("luma-kiosk.service", user=True), "active")
            self.assertIn("--user", run.call_args.args[0])
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/run/user/1234/bus")
            self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/1234")

    def test_no_user_bus_or_missing_systemctl_is_unavailable(self):
        with patch.object(smoke.Path, "is_socket", return_value=False), patch.object(smoke.subprocess, "run") as run:
            self.assertEqual(smoke.service_state("luma-kiosk.service", user=True), "unavailable")
            run.assert_not_called()
        with patch.object(smoke.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(smoke.service_state("luma-api.service"), "unavailable")

    def test_automated_success_never_qualifies_hardware(self):
        with patch.object(smoke.Path, "read_text", return_value="Raspberry Pi 4 Model B Rev 1.4\0"), \
                patch.object(smoke.platform, "machine", return_value="aarch64"), \
                patch.object(smoke.pwd, "getpwuid", return_value=SimpleNamespace(pw_name="luma")), \
                patch.object(smoke.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1234)), \
                patch.object(smoke.Path, "stat", return_value=SimpleNamespace(st_mode=0o40700, st_uid=1234)), \
                patch.object(smoke.shutil, "disk_usage", return_value=SimpleNamespace(free=2 * 1024**3)), \
                patch.object(smoke, "api_health", return_value=smoke.result("api_database", "pass", "ok")), \
                patch.object(smoke, "service_state", side_effect=lambda unit, **kw: (
                    "disabled" if kw.get("enabled") else "inactive") if "gateway" in unit else "active"):
            report = smoke.collect()
            self.assertTrue(report["automated_checks_passed"])
            self.assertFalse(report["hardware_qualified"])
            self.assertGreater(len(report["manual_gates_remaining"]), 0)

    def test_incomplete_host_never_passes_and_does_not_echo_identity(self):
        with patch.object(smoke.Path, "read_text", side_effect=FileNotFoundError), \
                patch.object(smoke.platform, "machine", return_value="x86_64"), \
                patch.object(smoke.pwd, "getpwuid", return_value=SimpleNamespace(pw_name="private-admin-name")), \
                patch.object(smoke.Path, "stat", side_effect=PermissionError("private-path")), \
                patch.object(smoke, "api_health", return_value=smoke.result("api_database", "fail", "offline")), \
                patch.object(smoke, "service_state", return_value="unavailable") as service:
            report = smoke.collect()
            self.assertFalse(report["automated_checks_passed"])
            self.assertFalse(report["hardware_qualified"])
            self.assertNotIn("private-admin-name", json.dumps(report))
            self.assertNotIn("private-path", json.dumps(report))
            self.assertFalse(any(call.kwargs.get("user") for call in service.call_args_list))
            by_name = {item["check"]: item["status"] for item in report["checks"]}
            self.assertEqual(by_name["luma-kiosk.service"], "skip")
            self.assertEqual(by_name["gateway_opt_in_default"], "fail")

    def test_cli_exit_code_tracks_automated_result_not_hardware_qualification(self):
        for passed in [True, False]:
            report = {"automated_checks_passed": passed, "hardware_qualified": False}
            with patch.object(smoke, "collect", return_value=report), patch("builtins.print") as output:
                self.assertEqual(smoke.main(), 0 if passed else 1)
                self.assertEqual(json.loads(output.call_args.args[0]), report)


if __name__ == "__main__":
    unittest.main()
