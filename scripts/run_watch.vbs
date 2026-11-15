' Compatibility launcher; first generate .pqc-schedule with install_schedule.py.
' This source stays ASCII so WScript does not misread UTF-8 comments.
Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(fs.GetParentFolderName(WScript.ScriptFullName))
runner = fs.BuildPath(root, ".pqc-schedule\run_watch.vbs")
If Not fs.FileExists(runner) Then WScript.Quit 2
WScript.Quit sh.Run("wscript.exe " & Chr(34) & runner & Chr(34), 0, True)
