' Task Scheduler entry: run one inbox scan with a hidden window (ASCII only: wscript reads ANSI).
' Child processes (python, ffmpeg, codex) share the hidden console, so no window flashes.
Set sh = CreateObject("WScript.Shell")
cmd = "cmd /c py -3 -X utf8 ""D:\secondbrain\Skills\phone-quick-cut\scripts\watch_inbox.py"" --once --agent codex > ""%TEMP%\pqc_watch.log"" 2>&1"
sh.Run cmd, 0, True
