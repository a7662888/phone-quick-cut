import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build
import deliver
import lyria_bgm
import pqc_common as common
import write_script
from intake import parse_brief
from analyze import pick_windows
import numpy as np


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {"id": "c1", "kind": "video", "in": 30.2, "dur": 1.9,
                          "scene": [30.2, 32.1], "src_dur": 36.0}
        self.index = {"candidates": [self.candidate]}
        self.script = {"title": "Test", "style": "溫馨", "ratio": "16:9", "voice": "zh-TW-YunJheNeural",
                       "shots": [{"cand": "c1", "dur": 1.9, "narration": ""}]}

    def test_valid_script(self):
        self.assertEqual(write_script.validate(self.script, self.index, {})[0], [])

    def test_short_explicit_target_is_preserved(self):
        self.assertEqual(parse_brief("十秒，不要旁白", "test")["target_seconds"], 10)

    def test_malformed_scripts_report_errors(self):
        cases = [None, {}, {**self.script, "shots": []}, {**self.script, "ratio": []},
                 {**self.script, "shots": [{"cand": ["c1"]}]},
                 {**self.script, "shots": [{"cand": "c1", "dur": float("inf")}]},
                 {**self.script, "shots": [{"cand": "c1", "narration": 1}]},
                 {**self.script, "shots": [{"cand": "c1", "dur": -1}]}]
        for value in cases:
            with self.subTest(value=value):
                self.assertTrue(write_script.validate(value, self.index, {})[0])

    def test_explicit_scene_escape_is_rejected(self):
        self.script["shots"][0]["in"] = 29.0
        self.assertTrue(write_script.validate(self.script, self.index, {})[0])
        with self.assertRaises(ValueError):
            build.plan(self.script, {"c1": self.candidate}, Path("unused"))

    def test_long_short_scene_never_crosses(self):
        self.script["shots"][0]["dur"] = 6.0
        self.assertTrue(write_script.validate(self.script, self.index, {})[0])
        with self.assertRaises(ValueError):
            build.plan(self.script, {"c1": self.candidate}, Path("unused"))

    def test_freeze_stays_inside_scene(self):
        self.script["shots"][0]["dur"] = 3.5
        shots, _ = build.plan(self.script, {"c1": self.candidate}, Path("unused"))
        shot = shots[0]
        self.assertLessEqual(shot["freeze"], 2.0)
        self.assertGreaterEqual(shot["in"], 30.2)
        self.assertLessEqual(shot["in"] + shot["len"] - shot["freeze"], 32.10001)

    def test_short_scenes_are_not_joined(self):
        cuts = [0.7, 1.4]
        picks = pick_windows(np.ones(4), 2.1, 5.0, cuts=cuts)
        self.assertTrue(picks)
        for start, length, _ in picks:
            self.assertFalse(any(start + .01 < cut < start + length - .01 for cut in cuts))

    def test_scene_render_does_not_read_extra_frames(self):
        self.candidate.update(path="input.mp4", w=320, h=180)
        shots, _ = build.plan(self.script, {"c1": self.candidate}, Path("unused"))
        with patch.object(build, "run") as run:
            build.render_shot(shots[0], 320, 180, "none", True, Path("out.mp4"), 27, "ultrafast")
        command = run.call_args.args[0]
        index = command.index("-t")
        self.assertAlmostEqual(float(command[index+1]), 1.9)

    def test_cloud_requires_opt_in_before_network(self):
        with patch.dict(os.environ, {"PQC_ALLOW_CLOUD": "0", "OPENROUTER_API_KEY": "fake-test-key"}):
            with self.assertRaises(RuntimeError):
                write_script.llm_complete("synthetic test")


class StandaloneResourceTests(unittest.TestCase):
    def test_tts_uses_the_verified_environment(self):
        with patch.object(common, "IS_WIN", True), patch.object(Path, "exists", return_value=True):
            self.assertEqual(common.edge_tts_cmd(), [sys.executable, "-m", "edge_tts"])

    def test_pronunciation_is_bundled_and_display_text_untouched(self):
        text = "馬偕四十週年"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(common.apply_pron(text), "馬街四十週年")
        self.assertEqual(text, "馬偕四十週年")

    def test_pronunciation_overrides_and_longest_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pron.json"
            p.write_text(json.dumps({"entries": [{"src": "AB", "say": "X"}, {"src": "A", "say": "Y"}]}), encoding="utf-8")
            with patch.dict(os.environ, {"PQC_PRONUNCIATION": str(p)}):
                self.assertEqual(common.apply_pron("ABA"), "XY")

    def test_auto_music_without_opt_in_stays_local_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PQC_ALLOW_PAID_MUSIC": "0", "OPENROUTER_API_KEY": "fake"}):
            with patch.object(build.subprocess, "run", side_effect=AssertionError("No external service allowed")):
                p = build.get_music({"style": "溫馨", "music": {"provider": "auto"}}, 1.0, Path(tmp))
                self.assertTrue(p.is_file())
                with patch.object(build, "synth_music", side_effect=AssertionError("Cache should be used")):
                    self.assertEqual(p, build.get_music({"style": "溫馨", "music": {"provider": "auto"}}, 1.0, Path(tmp)))

    def test_lyria_stream_chunks(self):
        value = b"a synthetic audio payload"
        encoded = base64.b64encode(value).decode()
        self.assertEqual(lyria_bgm.decode_audio([encoded[:7], encoded[7:]]), value)
        self.assertEqual(lyria_bgm.decode_audio([base64.b64encode(b"a").decode(), base64.b64encode(b"bc").decode()]), b"abc")

    def test_paid_music_cannot_run_from_key_alone(self):
        with patch.dict(os.environ, {"PQC_ALLOW_PAID_MUSIC": "0", "OPENROUTER_API_KEY": "fake"}):
            with self.assertRaises(RuntimeError):
                lyria_bgm.generate("test", Path("unused"), "test-model")


class DeliveryTests(unittest.TestCase):
    def test_delivery_requires_current_passed_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            dirs = common.project_dirs(project)
            final = dirs["out"] / "test.mp4"
            final.write_bytes(b"synthetic test file")
            common.write_json(dirs["out"] / "timeline.json", {"final": str(final), "total": 1})
            common.write_json(dirs["script"] / "brief.json", {})
            for qa in [{}, {"verdict": "FAIL", "fails": ["test"]},
                       {"verdict": "PASS", "file": str(final), "sha256": "stale"}]:
                common.write_json(dirs["qa"] / "qa.json", qa)
                with patch.object(sys, "argv", ["deliver.py", "--project", str(project)]), patch.object(deliver, "OUTBOX", Path(tmp)/"outbox"):
                    with self.assertRaises(SystemExit):
                        deliver.main()
                self.assertFalse((Path(tmp)/"outbox").exists())


if __name__ == "__main__":
    unittest.main()
