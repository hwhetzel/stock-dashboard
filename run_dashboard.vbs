Set oShell = CreateObject("WScript.Shell")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
oShell.Run """" & strDir & "venv\Scripts\pythonw.exe"" """ & strDir & "launcher.py""", 0, False