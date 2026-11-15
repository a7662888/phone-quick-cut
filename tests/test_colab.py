import ast
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
import types
import unittest
from unittest.mock import Mock, patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import make_colab_nb


def notebook_code(**inputs):
    nb = make_colab_nb.build_notebook()
    code = next(c["source"] for c in nb["cells"] if c["cell_type"] == "code")
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in inputs:
            node.value = ast.copy_location(ast.Constant(inputs[node.targets[0].id]), node.value)
    return compile(ast.fix_missing_locations(tree), "phone_quick_cut.ipynb", "exec"), tree


class NotebookTests(unittest.TestCase):
    def test_embedded_resources_equal_checkout(self):
        _, tree = notebook_code()
        blob = next(n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == "B" for t in n.targets))
        bundle = json.loads(zlib.decompress(base64.b64decode(blob)))
        self.assertIn("assets/pronunciation_zh.json", bundle)
        self.assertIn("requirements-musicgen.txt", bundle)
        for name, content in bundle.items():
            self.assertEqual(content, (ROOT/name).read_text(encoding="utf-8"), name)
            if name.endswith(".py"):
                ast.parse(content)

    def test_mount_exception_still_releases_runtime(self):
        drive = types.SimpleNamespace(mount=Mock(side_effect=RuntimeError("synthetic mount failure")), flush_and_unmount=Mock())
        runtime = types.SimpleNamespace(unassign=Mock())
        google = types.ModuleType("google")
        colab = types.ModuleType("google.colab")
        colab.drive, colab.runtime = drive, runtime
        google.colab = colab
        compiled, _ = notebook_code()
        with patch.dict(sys.modules, {"google":google, "google.colab":colab}), patch("time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            exec(compiled, {})
        runtime.unassign.assert_called_once()

    def test_failed_qa_cannot_copy_or_mark_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root/"drive"/"MyDrive"/"test"
            source.mkdir(parents=True)
            data=b"artificial source bytes; never opened by an image decoder"
            (source/"input.jpg").write_bytes(data)
            (source/"_source_manifest.json").write_text(json.dumps({"input.jpg":hashlib.sha256(data).hexdigest()}),encoding="utf-8")
            (source/"_script.json").write_text(json.dumps({"title":"Synthetic", "shots":[], "music":{}}),encoding="utf-8")
            project=root/"projects"/"test"
            scriptdir=project/"01_查核與腳本"
            scriptdir.mkdir(parents=True)
            (scriptdir/"brief.json").write_text("{}",encoding="utf-8")
            final=project/"synthetic.mp4"
            final.write_bytes(b"not a real video; fake runner output")
            qa_called=[]
            def invoke(cmd, **kwargs):
                command=list(map(str,cmd))
                if "intake.py" in command:
                    return subprocess.CompletedProcess(command,0,"PROJECT="+str(project)+"\n","")
                if "build.py" in command:
                    return subprocess.CompletedProcess(command,0,"FINAL="+str(final)+"\n","")
                if "review.py" in command:
                    qa_dir=project/"04_QA"
                    qa_dir.mkdir(exist_ok=True)
                    (qa_dir/"分鏡預覽.jpg").write_bytes(b"synthetic preview bytes")
                    return subprocess.CompletedProcess(command,0,"Synthetic reviewed script\n[review] preview\n","")
                if "qa.py" in command:
                    qa_called.append(True)
                    return subprocess.CompletedProcess(command,1,"", "synthetic QA FAIL")
                return subprocess.CompletedProcess(command,0,"","")
            def remap(value):
                s=str(value)
                if s.startswith("/content/drive"):
                    return root/"drive"/s.removeprefix("/content/drive/") if s!="/content/drive" else root/"drive"
                if s.startswith("/content/"):
                    return root/"content"/s.removeprefix("/content/")
                return Path(value)
            fakepath=types.ModuleType("pathlib")
            fakepath.Path=remap
            drive=types.SimpleNamespace(mount=Mock(),flush_and_unmount=Mock())
            runtime=types.SimpleNamespace(unassign=Mock())
            google=types.ModuleType("google")
            colab=types.ModuleType("google.colab")
            colab.drive,colab.runtime=drive,runtime
            google.colab=colab
            review_code,_=notebook_code(雲端硬碟資料夾="test",階段="重送目前稿（不重寫）",聲音="不要旁白",配樂=False)
            code,_=notebook_code(雲端硬碟資料夾="test",階段="台詞已確認，合成",聲音="不要旁白",配樂=False)
            captured = io.StringIO()
            with patch.dict(sys.modules,{"google":google,"google.colab":colab,"pathlib":fakepath}), patch.dict(os.environ), \
                 patch.object(sys,"path",list(sys.path)), patch("subprocess.run",side_effect=invoke), patch("time.sleep"), contextlib.redirect_stdout(captured):
                exec(review_code,{})
                self.assertTrue((source/"_狀態.txt").is_file(),captured.getvalue())
                self.assertIn("狀態：待審閱",(source/"_狀態.txt").read_text(encoding="utf-8"))
                self.assertEqual(json.loads((source/"_script.json").read_text(encoding="utf-8"))["title"],"Synthetic")
                self.assertFalse(qa_called)
                exec(code,{})
            self.assertTrue(qa_called)
            self.assertFalse((source/"成品").exists())
            self.assertIn("狀態：失敗",(source/"_狀態.txt").read_text(encoding="utf-8"))
            self.assertEqual(runtime.unassign.call_count,2)


if __name__ == "__main__": unittest.main()
