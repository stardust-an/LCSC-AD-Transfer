'=============================================================================
' LCSC-AD-Transfer -- Altium Designer One-Click Component Loader
'=============================================================================
' Auto-detects project directory. Auto-starts converter server.
' Opens SchDoc + PcbDoc + 3D step for each LCSC part number in AD tabs.
'
' Toolbar config:
'   ProjectName=...\AD-Plugin\LCSC-AD-Transfer.PrjScr
'   ProcName=lcsc_place.vbs
'=============================================================================

Option Explicit

Const CONVERTER_URL      = "http://localhost:3001"
Const SERVER_TIMEOUT     = 60000
Const SERVER_START_WAIT  = 10000

' Auto-detected at startup
Dim g_ProjectDir

'=============================================================================
' Main
'=============================================================================
Sub Main()
    Dim currentSheet, inputStr, codes, i, code, count, failCount

    On Error Resume Next
    Set currentSheet = SchServer.GetCurrentSchDocument
    On Error GoTo 0
    If currentSheet Is Nothing Then
        MsgBox "Please open a schematic document (*.SchDoc) first.", _
               vbExclamation, "LCSC-AD-Transfer"
        Exit Sub
    End If

    g_ProjectDir = FindProjectDir()
    If g_ProjectDir = "" Then
        MsgBox "Cannot find project directory." & vbCrLf & vbCrLf & _
               "Expected structure:" & vbCrLf & _
               "  .../LCSC-AD-Transfer/converter/server.js" & vbCrLf & vbCrLf & _
               "Ensure the .PrjScr file is inside the AD-Plugin folder.", _
               vbCritical, "LCSC-AD-Transfer"
        Exit Sub
    End If

    If Not EnsureServerRunning() Then
        MsgBox "Cannot start converter server." & vbCrLf & vbCrLf & _
               "Run manually: " & g_ProjectDir & "\start_server.bat", _
               vbCritical, "LCSC-AD-Transfer"
        Exit Sub
    End If

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

    On Error Resume Next
    Client.ShowDocument currentSheet
    On Error GoTo 0

    If count > 0 Then
        MsgBox "Opened " & count & " component tab(s)." & vbCrLf & vbCrLf & _
               "Ctrl+Tab -> component tab -> Ctrl+C" & vbCrLf & _
               "Ctrl+Tab -> schematic -> Ctrl+V -> click to place", _
               vbInformation, "LCSC-AD-Transfer"
    End If
End Sub

'=============================================================================
' Auto-detect project root directory
' Strategy:
'   1. Get .PrjScr project path from AD Client API -> walk up 2 levels
'   2. Fallback: search from current dir upward for converter\server.js
'   3. Fallback: scan common drive roots
'=============================================================================
Function FindProjectDir()
    Dim fso, dir

    Set fso = CreateObject("Scripting.FileSystemObject")

    ' ---- Method 1: Get project path from AD ----
    Dim proj, projPath
    On Error Resume Next
    Set proj = Client.GetCurrentProject
    If Not proj Is Nothing Then
        projPath = proj.DM_ProjectFullPath
        If Not IsEmpty(projPath) And projPath <> "" Then
            dir = fso.GetParentFolderName(projPath)         ' AD-Plugin\
            dir = fso.GetParentFolderName(dir)               ' project root
            If fso.FileExists(dir & "\converter\server.js") Then
                FindProjectDir = dir
                Exit Function
            End If
        End If
    End If
    On Error GoTo 0

    ' ---- Method 2: Walk up from working directory ----
    dir = fso.GetAbsolutePathName(".")
    Do While Len(dir) > 3
        If fso.FileExists(dir & "\converter\server.js") Then
            FindProjectDir = dir
            Exit Function
        End If
        Dim parent : parent = fso.GetParentFolderName(dir)
        If parent = dir Then Exit Do
        dir = parent
    Loop

    ' ---- Method 3: Scan common locations ----
    Dim roots, i
    roots = Array("D:\", "C:\", "E:\", "F:\")
    For i = 0 To UBound(roots)
        dir = roots(i)
        If fso.FolderExists(dir) Then
            FindProjectDir = ScanForProject(fso, dir, 2)
            If FindProjectDir <> "" Then Exit Function
        End If
    Next

    FindProjectDir = ""
End Function

Function ScanForProject(fso, baseDir, depth)
    If depth <= 0 Then
        ScanForProject = ""
        Exit Function
    End If

    Dim folder, subFolder
    On Error Resume Next
    Set folder = fso.GetFolder(baseDir)
    If folder Is Nothing Then
        ScanForProject = ""
        Exit Function
    End If

    For Each subFolder In folder.SubFolders
        If fso.FileExists(subFolder.Path & "\converter\server.js") Then
            ScanForProject = subFolder.Path
            Exit Function
        End If
        Dim found : found = ScanForProject(fso, subFolder.Path, depth - 1)
        If found <> "" Then
            ScanForProject = found
            Exit Function
        End If
    Next
    On Error GoTo 0

    ScanForProject = ""
End Function

'=============================================================================
' Auto-start converter server
'=============================================================================
Function EnsureServerRunning()
    Dim http, shell, fso, serverJs, cmd, startTime

    EnsureServerRunning = False

    If PingServer() Then
        EnsureServerRunning = True
        Exit Function
    End If

    ShowStatus "Starting converter server..."

    Set fso = CreateObject("Scripting.FileSystemObject")
    serverJs = g_ProjectDir & "\converter\server.js"
    If Not fso.FileExists(serverJs) Then
        ShowStatus "server.js not found: " & serverJs
        Exit Function
    End If

    On Error Resume Next
    Set shell = CreateObject("WScript.Shell")
    cmd = "cmd /c cd /d """ & fso.GetParentFolderName(serverJs) & _
          """ && start /min ""LCSC-Server"" node server.js"
    shell.Run cmd, 0, False
    On Error GoTo 0

    startTime = Timer
    Do While (Timer - startTime) * 1000 < SERVER_START_WAIT
        If PingServer() Then
            ShowStatus "Server started"
            EnsureServerRunning = True
            Exit Function
        End If
        shell.Run "ping -n 2 127.0.0.1 >nul", 0, True
    Loop

    ShowStatus "Server start timed out"
End Function

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
' Parse input, download, open files
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

'=============================================================================
' Link placed component's footprint to PcbLib file (Bocangku pattern)
'=============================================================================
Sub LinkFootprintToPcbLib(schRef, pcbLibPath, footprintName)
    Dim currentSheet, Iterator, Component, ImplIterator, schImpl

    If pcbLibPath = "" Then Exit Sub
    If SchServer Is Nothing Then Exit Sub

    On Error Resume Next
    Set currentSheet = SchServer.GetCurrentSchDocument
    If currentSheet Is Nothing Then Exit Sub

    ' Find the placed component by LibReference
    Set Iterator = currentSheet.SchIterator_Create
    Iterator.AddFilter_ObjectSet MkSet(eSchComponent)
    Set Component = Iterator.FirstSchObject
    Do While Not Component Is Nothing
        If LCase(Component.LibReference) = LCase(schRef) Then
            ' Found it — update footprint implementation
            Set ImplIterator = Component.SchIterator_Create
            ImplIterator.AddFilter_ObjectSet MkSet(eImplementation)
            Set schImpl = ImplIterator.FirstSchObject
            Do While Not schImpl Is Nothing
                If schImpl.ModelType = "PCBLIB" Then
                    schImpl.ModelName = footprintName
                    If schImpl.DatafileLinkCount > 0 Then
                        schImpl.DatafileLink(0).Location = pcbLibPath
                    End If
                End If
                Set schImpl = ImplIterator.NextSchObject
            Loop
            Component.SchIterator_Destroy ImplIterator
            Exit Do
        End If
        Set Component = Iterator.NextSchObject
    Loop
    currentSheet.SchIterator_Destroy Iterator
    currentSheet.GraphicallyInvalidate
    On Error GoTo 0
End Sub

Function DownloadAndOpen(lcscId)
    Dim response, parts, schPath, pcbPath, stepPath, title, pkg
    Dim binSchLibPath, binPcbLibPath
    Dim schDoc, pcbDoc, fso, schObj, currentSheet

    DownloadAndOpen = False

    response = GetFromServer(lcscId)
    If Left(response, 5) = "error" Then Exit Function

    parts = Split(response, "|")
    If UBound(parts) < 7 Then Exit Function

    ' Format: success|schLib|pcbLib|schDoc|pcbDoc|stepPath|title|package|uuid|binSchLib|binPcbLib
    schPath      = parts(3)   ' SchDoc (ASCII)
    pcbPath      = parts(4)   ' PcbDoc (ASCII)
    stepPath     = parts(5)   ' 3D model
    title        = parts(6)   ' Component name / LIBREFERENCE
    pkg          = parts(7)   ' Package name
    binSchLibPath = ""        ' Binary SchLib
    binPcbLibPath = ""        ' Binary PcbLib
    If UBound(parts) >= 9 Then binSchLibPath = parts(9)
    If UBound(parts) >= 10 Then binPcbLibPath = parts(10)

    Set fso = CreateObject("Scripting.FileSystemObject")

    ' ---- Try PlaceSchComponent with binary SchLib ----
    Dim placedOk : placedOk = False
    If binSchLibPath <> "" And fso.FileExists(binSchLibPath) Then
        On Error Resume Next
        Set currentSheet = SchServer.GetCurrentSchDocument
        If Not currentSheet Is Nothing Then
            currentSheet.PlaceSchComponent binSchLibPath, title, schObj
            If Not schObj Is Nothing Then
                ' Place left of origin to avoid overlapping existing components
                schObj.MoveByXY MilsToCoord(-3000), MilsToCoord(0)
                SchServer.GetCurrentSchDocument.GraphicallyInvalidate
                placedOk = True
            End If
        End If
        On Error GoTo 0
    End If

    ' ---- Post-placement: link footprint + open libraries ----
    If placedOk Then
        ' Find the placed component and link footprint to PcbLib file
        LinkFootprintToPcbLib title, binPcbLibPath, pkg

        ' Load SchLib + PcbLib into project (no view switch)
        If binSchLibPath <> "" And fso.FileExists(binSchLibPath) Then
            On Error Resume Next
            Client.OpenDocument "SchLib", binSchLibPath
            On Error GoTo 0
        End If
        If binPcbLibPath <> "" And fso.FileExists(binPcbLibPath) Then
            On Error Resume Next
            Client.OpenDocument "PcbLib", binPcbLibPath
            On Error GoTo 0
        End If
    Else
        ' ---- Fallback: open SchDoc + PcbDoc as AD tabs ----
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
    End If

    Dim has3D, statusMsg
    has3D = (stepPath <> "" And fso.FileExists(stepPath))
    If placedOk Then
        statusMsg = "[" & lcscId & "] " & title & " (" & pkg & ") -- Placed on schematic"
    Else
        statusMsg = "[" & lcscId & "] " & title & " (" & pkg & ") -- SCH+PCB opened"
    End If
    If has3D Then statusMsg = statusMsg & "+3D"
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
    ' Intentionally empty — avoids AD ShowMessage popups
End Sub
