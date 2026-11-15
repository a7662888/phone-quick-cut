"""Offline generated-media acceptance test. Never reads a real inbox or calls a model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def exercise(root):
    import numpy as np
    from PIL import Image
    root = Path(root).resolve()
    inbox = root / "inbox" / "generated"
    inbox.mkdir(parents=True)
    arr = np.zeros((180, 320, 3), dtype=np.uint8)
    arr[:, :, 0] = np.linspace(40, 240, 320, dtype=np.uint8)
    arr[:, :, 1] = np.linspace(40, 220, 180, dtype=np.uint8)[:, None]
    arr[:, :, 2] = 130
    for i in range(2):
        Image.fromarray(np.roll(arr, i * 50, axis=1)).save(inbox / f"generated_{i}.jpg")
    env = {k:v for k,v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "COLAB_RELEASE_TAG")}
    env.update(PQC_INBOX=str(root/"inbox"), PQC_OUTBOX=str(root/"outbox"), PQC_VIDEO=str(root/"projects"),
               PQC_ALLOW_CLOUD="0", PQC_ALLOW_PAID_MUSIC="0", PYTHONUTF8="1")
    def execute(script, *args, expect=0):
        r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT/"scripts"/script), *map(str,args)],
                           env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        with (root/"smoke.log").open("a",encoding="utf-8") as log:
            log.write(f"{script} {args}\n{r.stdout}\n{r.stderr}\n")
        if r.returncode != expect:
            raise AssertionError(f"{script} returned {r.returncode}, expected {expect}: {r.stderr[-1800:]}")
        return r
    # Two visibly different scenes ensure cut-aware selection is exercised without speech models.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=320x180:d=2:r=30",
                    "-f", "lavfi", "-i", "color=blue:s=320x180:d=2:r=30", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(inbox/"generated_cut.mp4")],
                   check=True, capture_output=True, timeout=60)
    (inbox/"任務.txt").write_text("主題是移植測試，溫馨風格，十五秒，橫式，不要音樂，不要旁白。",encoding="utf-8")
    execute("run_job.py", "--src", inbox, "--mode", "manual", "--no-speech")
    assert "狀態：待寫稿" in (inbox/"_狀態.txt").read_text(encoding="utf-8")
    project = next((root/"projects").iterdir())
    scriptdir = project/"01_查核與腳本"
    assert not (scriptdir/"script.json").exists()
    assert (scriptdir/"script_request.md").is_file()
    index = json.loads((project/"02_素材"/"media_index.json").read_text(encoding="utf-8"))
    videos = [c for c in index["candidates"] if c["kind"] == "video"]
    assert videos, "Generated video must have candidates"
    assert all(c["in"] + c["dur"] <= c["scene"][1] + .02 for c in videos)
    execute("write_script.py", "--project", project, "--mode", "template")
    script = scriptdir/"script.json"
    content = json.loads(script.read_text(encoding="utf-8"))
    chosen = videos[0]
    content["shots"].append({"cand":chosen["id"], "dur":3.5, "narration":"", "caption":"同一鏡頭"})
    content["title_pos"] = "top"
    script.write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding="utf-8")
    execute("run_job.py", "--project", project, "--submit-script")
    assert "狀態：待審閱" in (inbox/"_狀態.txt").read_text(encoding="utf-8")
    original = script.read_text(encoding="utf-8")
    script.write_text(original + "\n",encoding="utf-8")
    execute("run_job.py", "--project", project, "--approve", expect=2)
    assert not (root/"outbox").exists(), "Unreviewed edits must not be delivered"
    script.write_text(original,encoding="utf-8")
    execute("run_job.py", "--project", project, "--approve", "--draft")
    qa=json.loads((project/"04_QA"/"qa.json").read_text(encoding="utf-8"))
    assert qa["verdict"] == "PASS", qa
    assert not qa["warns"], qa["warns"]
    final=Path(qa["file"])
    timeline=json.loads((project/"03_成片"/"timeline.json").read_text(encoding="utf-8"))
    rendered=next(s for s in timeline["shots"] if s["cand"]==chosen["id"])
    assert rendered["freeze"] > 0
    assert rendered["in"]+rendered["len"]-rendered["freeze"] <= chosen["scene"][1]+.01
    # Sample the frozen tail: it must still be the selected red scene, not the following blue scene.
    sample=subprocess.run(["ffmpeg","-v","error","-ss",str(rendered["start"]+3.0),"-i",str(final),
                           "-frames:v","1","-vf","scale=1:1","-pix_fmt","rgb24","-f","rawvideo","-"],
                          capture_output=True,check=True,timeout=30).stdout
    assert len(sample)==3 and sample[0]>sample[2]*2, "Frozen tail leaked the following scene"
    assert list((root/"outbox").glob("*.mp4"))
    assert list((root/"outbox").glob("*.srt"))
    assert "狀態：完成" in (inbox/"_狀態.txt").read_text(encoding="utf-8")
    # A stale QA report cannot authorize a modified output with the same filename.
    with final.open("ab") as handle: handle.write(b"changed-after-qa")
    execute("deliver.py", "--project", project, expect=1)
    result={"verdict":"PASS", "duration":qa["duration"], "candidates":len(index["candidates"]),
            "manual_review_approval":True, "scene_bounds":True, "stale_qa_rejected":True}
    print(json.dumps(result,ensure_ascii=False))
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--keep",type=Path,help="Keep synthetic test artifacts in a new directory")
    a=ap.parse_args()
    if a.keep:
        if a.keep.exists(): raise SystemExit("--keep must name a new directory")
        a.keep.mkdir(parents=True)
        exercise(a.keep)
    else:
        with tempfile.TemporaryDirectory(prefix="pqc-smoke-") as tmp: exercise(tmp)


if __name__ == "__main__": main()
