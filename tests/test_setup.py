"""Portability checks without package installation, authentication or scheduler changes."""
import contextlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_schedule
import setup_env


class DoctorTests(unittest.TestCase):
    def test_required_failures_return_nonzero(self):
        with patch.object(setup_env, "doctor", return_value={"ok": False, "checks": [], "paths": {}}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup_env.main([]), 1)

    def test_successful_json_is_machine_readable(self):
        stdout = io.StringIO()
        with patch.object(setup_env, "doctor", return_value={"ok": True, "checks": [], "paths": {}}), contextlib.redirect_stdout(stdout):
            self.assertEqual(setup_env.main(["--json"]), 0)
        self.assertTrue(json.loads(stdout.getvalue())["ok"])

    def test_missing_dependency_is_not_a_pass(self):
        with patch.object(setup_env, "requirements", return_value=iter([("numpy", [(">=", "1.26"), ("<", "3")])])), patch.object(setup_env.importlib.metadata, "version", side_effect=importlib.metadata.PackageNotFoundError):
            self.assertFalse(setup_env.check_modules()[0]["ok"])

    def test_incompatible_dependency_fails_before_import(self):
        with patch.object(setup_env, "requirements", return_value=iter([("numpy", [(">=", "1.26"), ("<", "3")])])), patch.object(setup_env.importlib.metadata, "version", return_value="3.0.0"), patch.object(setup_env.importlib.util, "find_spec", return_value=object()), patch.object(setup_env, "invoke") as invoke:
            self.assertFalse(setup_env.check_modules()[0]["ok"])
            invoke.assert_not_called()

    def test_binary_import_error_is_a_failure(self):
        with patch.object(setup_env, "requirements", return_value=iter([("numpy", [(">=", "1.26"), ("<", "3")])])), patch.object(setup_env.importlib.metadata, "version", return_value="2.2.0"), patch.object(setup_env.importlib.util, "find_spec", return_value=object()), patch.object(setup_env, "invoke", return_value=subprocess.CompletedProcess([], 1, "", "broken")):
            self.assertFalse(setup_env.check_modules()[0]["ok"])

    def test_install_targets_only_a_verified_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "venv"
            python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(setup_env, "invoke", return_value=subprocess.CompletedProcess([], 0, "1\n", "")), patch.object(setup_env.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), patch("pqc_common.INBOX", Path(tmp) / "in"), patch("pqc_common.OUTBOX", Path(tmp) / "out"), patch("pqc_common.VIDEO_ROOT", Path(tmp) / "projects") as _:
                setup_env.install_in_venv(target)
                calls = setup_env.subprocess.run.call_args_list
            pip = calls[0].args[0]
            self.assertEqual(pip[:4], [str(python.resolve()), "-m", "pip", "install"])
            self.assertNotEqual(pip[0], sys.executable)

    def test_global_python_cannot_masquerade_as_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "venv"
            python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(setup_env, "invoke", return_value=subprocess.CompletedProcess([], 0, "0\n", "")), patch.object(setup_env.subprocess, "run") as run:
                with self.assertRaises(RuntimeError):
                    setup_env.install_in_venv(target)
                run.assert_not_called()

    def test_ffmpeg_present_but_without_subtitles_is_failure(self):
        outputs = [subprocess.CompletedProcess([], 0, "scale overlay zoompan loudnorm sidechaincompress tpad", ""),
                   subprocess.CompletedProcess([], 0, "libx264 aac", ""), subprocess.CompletedProcess([], 0, "ffprobe", "")]
        with patch.object(setup_env.shutil, "which", side_effect=lambda name: "/tools/" + name), patch.object(setup_env, "invoke", side_effect=outputs):
            checks = setup_env.check_ffmpeg()
        self.assertFalse(next(x for x in checks if x["name"] == "ffmpeg_filters")["ok"])

    def test_cli_auth_uses_safe_command_prefix_without_batch_shell(self):
        with patch("pqc_common.agent_command", return_value=["node", "C:/npm path/codex.js"]), patch.object(setup_env, "invoke", return_value=subprocess.CompletedProcess([], 0, "", "")) as invoke:
            self.assertTrue(setup_env.check_agent("codex")["ok"])
        self.assertEqual(invoke.call_args.args[0], ["node", "C:/npm path/codex.js", "login", "status"])

    def test_auth_json_does_not_treat_logged_out_claude_as_success(self):
        with patch("pqc_common.agent_command", return_value=["claude"]), patch.object(setup_env, "invoke", return_value=subprocess.CompletedProcess([], 0, '{"loggedIn": false}', "")):
            self.assertFalse(setup_env.check_agent("claude")["ok"])


class SchedulerTests(unittest.TestCase):
    def test_generated_runner_preserves_configured_tool_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PATH": "/custom/ffmpeg-full/bin"}):
            install_schedule.generate(Path(tmp)/"schedule")
            config=json.loads((Path(tmp)/"schedule"/"config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["environment"]["PATH"], "/custom/ffmpeg-full/bin")

    def test_generated_runner_executes_with_space_ampersand_and_cjk_paths(self):
        with tempfile.TemporaryDirectory(prefix="pqc runner 測試 & ") as tmp:
            base = Path(tmp)
            repo = base / "repo & 中文"
            (repo / "scripts").mkdir(parents=True)
            watcher = 'import json,os,sys;print(json.dumps({"args":sys.argv[1:],"inbox":os.environ["PQC_INBOX"]}))'
            (repo / "scripts" / "watch_inbox.py").write_text(watcher, encoding="utf-8")
            with patch("pqc_common.INBOX", base / "手機收件匣"), patch("pqc_common.OUTBOX", base / "成品"), patch("pqc_common.VIDEO_ROOT", base / "projects"):
                out = install_schedule.generate(base / "generated", "codex", repo)
            r = subprocess.run([sys.executable, "-X", "utf8", str(out / "runner.py")], capture_output=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            log = json.loads((out / "watch.log").read_text(encoding="utf-8"))
            self.assertEqual(log["args"], ["--once", "--agent", "codex"])
            self.assertEqual(log["inbox"], str((base / "手機收件匣").resolve()))

    def test_generation_keeps_paths_and_secrets_out_of_commands(self):
        with tempfile.TemporaryDirectory(prefix="pqc path & ") as tmp:
            base = Path(tmp)
            env = {"PQC_INBOX": str(base / "手機收件匣"), "PQC_API_KEY": "DO_NOT_PERSIST", "PQC_STYLE": "溫馨"}
            with patch.dict(os.environ, env), patch("pqc_common.INBOX", base / "手機收件匣"), patch("pqc_common.OUTBOX", base / "成品"), patch("pqc_common.VIDEO_ROOT", base / "projects"):
                out = install_schedule.generate(base / "generated", "codex", base / "repo & folder", base / "python & folder" / "python.exe")
            config = json.loads((out / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["environment"]["PQC_INBOX"], str((base / "手機收件匣").resolve()))
            self.assertNotIn("PQC_API_KEY", config["environment"])
            self.assertIn("PQC_STYLE", config["environment"])
            (out / "run_watch.vbs").read_bytes().decode("ascii")
            xml = ET.fromstring((out / "task.xml").read_bytes())
            ns = {"t": install_schedule.TASK_NS}
            self.assertEqual(xml.find("t:Actions/t:Exec/t:Arguments", ns).text, '"' + str(out / "run_watch.vbs") + '"')
            self.assertNotIn("shell=True", (out / "runner.py").read_text())

    def test_unowned_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "runner.py").write_text("untouched", encoding="utf-8")
            with self.assertRaises(ValueError):
                install_schedule.generate(tmp)
            self.assertEqual(Path(tmp, "runner.py").read_text(), "untouched")

    def test_existing_unowned_task_cannot_be_overwritten(self):
        xml = f'<Task xmlns="{install_schedule.TASK_NS}"><RegistrationInfo><Description>Another application</Description></RegistrationInfo></Task>'
        with patch.object(install_schedule.os, "name", "nt"), patch.object(install_schedule.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, xml, "")) as run:
            with self.assertRaises(RuntimeError):
                install_schedule.register_windows_task("unused", replace=True)
            self.assertEqual(run.call_count, 1)

    def test_default_generation_does_not_register_a_task(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(install_schedule, "register_windows_task") as register, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install_schedule.main(["--output", str(Path(tmp) / "generated")]), 0)
            register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
