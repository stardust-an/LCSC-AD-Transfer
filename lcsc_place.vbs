'=============================================================================
' LCSC-AD-Transfer v8 -- Auto-start server + Open SchDoc & PcbDoc
'=============================================================================
' Checks if local converter server is running. If not, starts it automatically.
' Then downloads and opens SchDoc + PcbDoc in AD for each LCSC part number.
'
' Config: Edit PROJECT_DIR below if you moved the project folder.
'=============================================================================

Option Explicit

' ---- User Configuration ----------------------------------------------------
Const PROJECT_DIR    = "D:\Download\LCSC-AD-Transfer"   ' Change if you moved the project
Const CONVERTER_URL  = "http://localhost:3001"
Const SERVER_TIMEOUT = 60000
Const SERVER_START_WAIT = 10000   ' Max wait for server to start (ms)

'=============================================================================
' Main
'=============================================================================
Sub Main()
    Dim currentSheet, inputStr, codes, i, code, count, failCount

    ' Ensure schematic is open
    On Error Resume Next
    Set currentSheet = SchServer.GetCurrentSchDocument
    On Error GoTo 0
    If currentSheet Is Nothing Then
        MsgBox "Please open a schematic document (*.SchDoc) first.", _
               vbExclamation, "LCSC-AD-Transfer"
        Exit Sub
    End If

    ' Auto-start server if needed
    If Not EnsureServerRunning() Then
        MsgBox "Cannot start converter server." & vbCrLf & vbCrLf & _
               "Please start manually: double-click start_server.bat" & vbCrLf & _
               "Project dir: " & PROJECT_DIR, vbCritical, "LCSC-AD-Transfer"
        Exit Sub
    End If

    ' Get input
    inputStr = InputBox( _
        "Enter LCSC part number(s)" & vbCrLf & _
        "(comma/space/semicolon separated):" & vbCrLf & vbCrLf & _
        "  Single: C8734" & vbCrLf & _
        "  Multi:  C8734, C2040, C5446" & vbCrLf & vbCrLf & _
        "SchDoc + PcbDoc will open as AD tabs." & vbCrLf & _
        "Use Ctrl+C / Ctrl+V to place on schematic.", _
        "LCSC-AD-Transfer", "")

    If inputStr = "" Then Exit Sub

    codes = ParseCodes(inputStr)
    If UBound(codes) < 0 Then Exit Sub

    count = 0 : failCount = 0
    For i = 0 To UBound(codes)
        code = Trim(codes(i))
        If code <> "" Then
            If DownloadAndOpen(code) Then count = count + 1 Else failCount = failCount + 1
        End If
    Next

    ' Go back to user schematic
    On Error Resume Next
    Client.ShowDocument currentSheet
    On Error GoTo 0

    If count > 0 Then
        MsgBox "Opened " & count & " component tab(s)." & vbCrLf & vbCrLf & _
               "Ctrl+Tab -> component tab -> Ctrl+C" & vbCrLf & _
               "Ctrl+Tab -> schematic -> Ctrl+V -> click to place" & vbCrLf & vbCrLf & _
               "Temp files: " & GetTempDir(), vbInformation, "LCSC-AD-Transfer"
    End If
End Sub

'=============================================================================
' Auto-start server
'=============================================================================
Function EnsureServerRunning()
    Dim http, shell, fso, batPath, cmd, startTime

    EnsureServerRunning = False

    ' Quick check: is server already running?
    If PingServer() Then
        EnsureServerRunning = True
        Exit Function
    End If

    ShowStatus "Server not running, attempting auto-start..."

    ' Find start_server.bat
    Set fso = CreateObject("Scripting.FileSystemObject")
    batPath = PROJECT_DIR & "\start_server.bat"
    If Not fso.FileExists(batPath) Then
        ' Try relative to current dir
        batPath = fso.GetAbsolutePathName(".") & "\start_server.bat"
        If Not fso.FileExists(batPath) Then
            ShowStatus "Cannot find start_server.bat"
            Exit Function
        End If
    End If

    ' Start server (hidden window)
    On Error Resume Next
    Set shell = CreateObject("WScript.Shell")
    cmd = "cmd /c cd /d """ & fso.GetParentFolderName(batPath) & _
          "\converter"" && start /min ""LCSC-Server"" node server.js"
    shell.Run cmd, 0, False
    On Error GoTo 0

    ' Wait for server to become ready
    startTime = Timer
    Do While (Timer - startTime) * 1000 < SERVER_START_WAIT
        If PingServer() Then
            ShowStatus "Server started successfully"
            EnsureServerRunning = True
            Exit Function
        End If
        ' Sleep ~1 second using ping trick (VBScript has no native sleep)
        shell.Run "ping -n 2 127.0.0.1 >nul", 0, True
    Loop

    ShowStatus "Server start timed out"
End Function

'=============================================================================
' Quick HTTP ping to check if server is alive
'=============================================================================
Function PingServer()
    Dim http
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
    If http Is Nothing Then Set http = CreateObject("MSXML2.XMLHTTP")
    If http Is Nothing Then
        PingServer = False
        Exit Function
    End If

    http.Open "GET", CONVERTER_URL & "/", False
    http.SetTimeouts 3000, 3000, 3000, 3000
    http.Send

    PingServer = (http.Status = 200)
    Set http = Nothing
    On Error GoTo 0
End Function

'=============================================================================
' Helpers
'=============================================================================
Function ParseCodes(inputStr)
    Dim s
    s = Replace(inputStr, ";", ",")
    s = Replace(s, " ", ",")
    s = Replace(s, vbTab, ",")
    Do While InStr(s, ",,") > 0
        s = Replace(s, ",,", ",")
    Loop
    If Left(s, 1) = "," Then s = Mid(s, 2)
    If Right(s, 1) = "," Then s = Left(s, Len(s) - 1)
    ParseCodes = Split(s, ",")
End Function

Function GetTempDir()
    Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
    GetTempDir = fso.GetSpecialFolder(2) & "\LCSC-AD-Transfer\"
End Function

Function DownloadAndOpen(lcscId)
    Dim response, parts, schPath, pcbPath, stepPath, title, pkg
    Dim schDoc, pcbDoc, fso

    DownloadAndOpen = False

    response = GetFromServer(lcscId)
    If Left(response, 5) = "error" Then Exit Function

    parts = Split(response, "|")
    If UBound(parts) < 7 Then Exit Function

    ' Format: success|schLib|pcbLib|schDoc|pcbDoc|stepPath|title|package|uuid
    schPath  = parts(3)
    pcbPath  = parts(4)
    stepPath = parts(5)
    title    = parts(6)
    pkg      = parts(7)

    Set fso = CreateObject("Scripting.FileSystemObject")

    If fso.FileExists(schPath) Then
        On Error Resume Next
        Set schDoc = Client.OpenDocument("SCH", schPath)
        If Not schDoc Is Nothing Then Client.ShowDocument schDoc
        On Error GoTo 0
    End If

    If fso.FileExists(pcbPath) Then
        On Error Resume Next
        Set pcbDoc = Client.OpenDocument("PCB", pcbPath)
        If Not pcbDoc Is Nothing Then Client.ShowDocument pcbDoc
        On Error GoTo 0
    End If

    Dim has3D, statusMsg
    has3D = (stepPath <> "" And fso.FileExists(stepPath))
    statusMsg = "[" & lcscId & "] " & title & " (" & pkg & ") -- SCH+PCB"
    If has3D Then statusMsg = statusMsg & "+3D"
    statusMsg = statusMsg & " opened"
    ShowStatus statusMsg
    DownloadAndOpen = True
End Function

Function GetFromServer(lcscId)
    Dim http, url
    url = CONVERTER_URL & "/ad-place/" & lcscId

    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
    If http Is Nothing Then Set http = CreateObject("MSXML2.XMLHTTP")
    If http Is Nothing Then Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    If http Is Nothing Then
        GetFromServer = "error|Cannot create HTTP object"
        Exit Function
    End If

    http.Open "GET", url, False
    http.SetTimeouts SERVER_TIMEOUT, SERVER_TIMEOUT, SERVER_TIMEOUT, SERVER_TIMEOUT
    http.Send

    If http.Status = 200 Then
        GetFromServer = http.ResponseText
    Else
        GetFromServer = "error|HTTP " & http.Status
    End If
    Set http = Nothing
    On Error GoTo 0
End Function

Sub ShowStatus(msg)
    On Error Resume Next
    ShowMessage msg
    On Error GoTo 0
End Sub
