---
name: ad-plugin-vbscript-pattern
description: Altium Designer 插件必须用 VBScript 而非 JScript 的原因和实践模式
metadata:
  type: project
---

# AD 插件 VBScript 模式

## 为什么用 VBScript 而不是 JScript

- AD 22+ 中 JScript 引擎有问题，插件可能无响应
- JScript `.PrjScr` 可能报 "Unrecognized project Fire Version"
- VBScript 是 AD 官方推荐并完全支持的脚本语言
- 参考项目 bocang-v1.0 国创库插件也使用 `.vbs` 模式

## AD 中运行 VBScript 的方式

### 方式 1：直接运行（推荐用于开发调试）
`文件` → `运行脚本...` → 文件类型选 `VBScript (*.vbs)` → 选择 .vbs 文件

### 方式 2：工具栏按钮（推荐用于日常使用）
AD 工具栏右键 → Customize → 新建按钮：
```
ProjectName=...\AD-Plugin\LCSC-AD-Transfer.PrjScr
ProcName=lcsc_place.vbs
```
`ProcName` 指定 `.PrjScr` 文件中的一个 procedure/module 名称。

### 方式 3：通过 .PrjScr 项目文件
`.PrjScr` 文件引用 `.vbs` 作为 module，通过 `ProcName` 指定入口。

## 插件通信模式

VBScript 通过 HTTP 与本地 Node.js 服务通信：
```vbscript
Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
http.Open "GET", "http://localhost:3001/ad-place/" & lcscNumber, True
http.Send
' ... 处理响应 ...
```

比文件 JSON 更可靠，因为：
- 不需要复杂 JSON 解析（VBScript JSON 解析有限）
- 实时响应，无需轮询文件
- 服务端可以做更复杂的转换

## 关键 VBScript AD API

```vbscript
' 检查原理图是否打开
Set currentSheet = SchServer.GetCurrentSchDocument

' 获取脚本项目路径（比 GetCurrentProject 更可靠）
Set scriptSys = Client.GetScriptingSystem
Set sp = scriptSys.CurrentScriptProject          ' 或 ScriptProject(0)
projPath = sp.DM_ProjectFullPath

' 放置元件（⚠️ 仅 AD26+ 支持二进制 SchLib）
currentSheet.PlaceSchComponent schLibPath, compName, SchObject

' 打开文档
Set doc = Client.OpenDocument("Sch", filePath)
Client.ShowDocument(doc)

' 坐标转换
MilsToCoord(mils)    ' mils → AD 内部单位
mmToCoord(mm)        ' mm → AD 内部单位
```

## PlaceSchComponent 跨版本兼容性

**关键发现 (2026-06-22)**: `PlaceSchComponent` 在不同 AD 版本中行为不同：

| AD 版本 | 二进制 SchLib | ASCII SchLib |
|---------|-------------|------------|
| AD26+ | ✅ 支持 | ✅ 可能支持 |
| AD25 | ❌ 不支持 | ❌ 不支持 |
| AD24 | ❌ 不支持 | ❌ 不支持 |

二进制文件由 `altium-monkey>=2026.6.9` 生成，格式较新，老版本 AD 不兼容。
ASCII SchLib 的 `PlaceSchComponent` 在 AD24/25 中返回 Nothing（放置失败）。

### 当前放置策略（多级回退）
1. 二进制 SchLib → `PlaceSchComponent`（AD26+）
2. AD 进程命令 `SCH:PlaceComponent`（实验性）
3. SchDoc 复制 → 粘贴（实验性）
4. 打开 SchLib + PcbLib 库文件（用户手动放置）
5. 打开 SchDoc + PcbDoc（最终兜底）

### FindProjectDir 改进 (2026-06-22)
原实现只用 `Client.GetCurrentProject`，但它返回的是 PCB 项目（`.PrjPcb`）而非脚本项目（`.PrjScr`）。修复：
- **Method 0**: 使用 `Client.GetScriptingSystem` 获取脚本项目路径（最可靠）
- **Method 1**: 区分 PrjScr 和 PrjPcb，向上走不同层数
- **Method 3**: 扫描深度从 2 提高到 4（覆盖深层路径如 `C:\Users\...\Downloads\...`）

### 调试日志系统
VBScript 中 MsgBox 有字符限制（约 1024 字符），完整调试报告应写入文件：
```vbscript
Dim g_DebugLog : g_DebugLog = ""
Sub DebugSilent(msg) : g_DebugLog = g_DebugLog & msg & vbCrLf : End Sub
Sub ShowDebugReport()
    Set f = fso.CreateTextFile(logPath, True)
    f.Write g_DebugLog : f.Close
End Sub
```

## 参考

- bocang-v1.0 Bocangku.vbs — 国创库插件完整 VBScript 实现
- Altium API 文档: https://techdocs.altium.com/display/SCRT/Altium+Designer+API
