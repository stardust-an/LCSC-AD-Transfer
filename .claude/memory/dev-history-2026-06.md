---
name: dev-history-2026-06
description: 2026年6月开发历程：从 Python 图元解析方案到 jsapi.min.js VBScript 方案
metadata:
  type: project
---

# 2026年6月开发历程

## 方案演进

### 方案 A：Python 图元解析 + AD JScript API（已废弃）
- Python 后端解析 EasyEDA 图元（复用 JLC2KiCadLib 的 handler 模式）
- AD JScript 插件读取 JSON，通过 AD API 创建 SchLib/PcbLib
- **废弃原因**：
  1. JScript 在 AD 22+ 中无响应，报 "Unrecognized project Fire Version"
  2. 手动解析 20+ 种图元类型精度不如 jsapi.min.js 官方引擎
  3. AD API 创建库组件的复杂度远超预期

### 方案 B：VBScript + Node.js 转换服务（当前方案）
- Node.js + jsapi.min.js 官方引擎负责转换
- VBScript 插件只负责调用 API 和打开生成的文件
- **参考**：bocang-v1.0 国创库插件（VBScript + 本地 HTTP 服务 + 定时器轮询）
- **优点**：转换精度最高、AD 兼容性最好、插件代码简洁

## 关键决策

1. **VBScript 而非 JScript**：AD 22+ 官方推荐 VBScript，JScript 引擎有兼容性问题
2. **jsapi.min.js 而非手动解析**：官方引擎经过验证，覆盖全部元件类型
3. **本地 HTTP 服务而非文件通信**：避免 VBScript JSON 解析的 64 位兼容问题和文件轮询
4. **trust_env = False**：系统代理会导致 easyeda.com 连接失败
5. **Altium ASCII 5.0 输出**：兼容性最好的格式，AD 17+ 全部可通过导入向导打开
6. **不自动放置，改为打开文件标签页**：AD API `PlaceSchComponent` 要求二进制格式库文件，ASCII 格式文件通过剪贴板复制最可靠







## AD24/AD25 兼容性调试 (2026-06-22)

### 问题
AD26 上一键放置元件正常，但 AD24 上只打开 SchDoc/PcbDoc，不放置元件，SchLib/PcbLib 打开后为空。

### 调试过程与发现

1. **FindProjectDir 失败** → 修复了项目目录自动检测（见 [[ad-plugin-vbscript-pattern]] Method 0）

2. **ASCII SchLib/PcbLib 为空** → 修复了 `schDocToSchLib`（INDEXINSHEET 未移除）和 `pcbDocToPcbLib`（坐标未归一化），见 [[conversion-pipeline]]

3. **二进制覆盖 ASCII 回退文件** → `ascii2binary.py` 的 `-o` 参数与 ASCII SchLib 路径相同，二进制生成后覆盖了 ASCII 文件。修复：二进制输出改为 `.bin` 后缀

4. **PlaceSchComponent 在 AD24 完全不工作** → 发现 `PlaceSchComponent` 在 AD24 中不支持 ASCII SchLib（返回 Nothing），二进制 SchLib（由 altium-monkey>=2026.6.9 生成）也因格式太新而被拒绝

5. **AD 进程命令 (SCH:PlaceComponent, SCH:SelectAll, SCH:Copy, SCH:Paste) 执行但无效果** → 尝试了多种进程变体（不同参数、不同进程名、WorkspaceManager）均未能实际放置/粘贴元件

### 当前状态
- AD26: 一键放置正常工作（二进制 PlaceSchComponent）
- AD24: 自动放置尚未解决，但 SchLib+PcbLib 可以正常打开（库面板显示元件，用户可手动放置）
- 仍有 Attempt 2（SCH:PlaceComponent 进程）和 Attempt 3（SchDoc 复制粘贴）待验证

### 待解决问题
- AD24 中自动放置的方法（可能需要编译 IntLib 或找到正确的 API）
- `SCH:Paste` 后元件可能处于浮动状态，需要 `SCH:Accept` 或鼠标单击确认










## 依赖检测与报错提示 (2026-06-22)

### 问题
AD26 上一键放置元件正常（二进制 SchLib/PcbLib），但 AD24 上只生成 ASCII 格式文件，无法打开。

### 根因：缺少 altium-monkey 依赖，脚本和服务无任何报错提示
服务器 `server.js` 的二进制转换依赖 `altium-monkey` Python 库。该电脑未安装 `altium-monkey`，但脚本和服务**静默跳过**了二进制转换（`HAS_BINARY_CONVERTER = false`），回退到 ASCII 格式，用户完全不知道缺少了什么依赖。

### 次级问题：安装 altium-monkey 过程中遇到的环境障碍
`pip install altium-monkey` 需要 Python 3.11–3.12，而该电脑存在多个环境问题：
1. **pyenv 3.12.9 缺少 python.exe**：初始安装只有 `python_d.exe`（调试构建），需重装修复
2. **Node.js execFileSync 不走 pyenv shim**：`execFileSync("python")` 直接找到系统 Python 3.8.5，而非 pyenv 的 3.12.9
3. **版本检查只认 3.11**：`server.js` 的 `includes("3.11")` 硬编码，3.12 被跳过

这些不是根因——即使是完美的 Python 环境，只要 `altium-monkey` 没装上，二进制转换就不会工作。它们只是在「装不上」之上叠加了额外阻力。

### 修复：让缺失依赖可见

#### server.js — 启动时检测并报错
- `_resolvePython()` 函数：使用 `cmd /c` 检测 Python 版本（兼容 pyenv shim），通过 `pyenv which` 解析为绝对 exe 路径；版本检查同时接受 3.11 和 3.12
- 新增 `altium-monkey` 导入检测：启动时 `import altium_monkey`，失败则 `console.error` 红色报错并显示安装命令
- `HAS_BINARY_CONVERTER` 现在需要三个条件：Python 3.11/3.12 + 脚本存在 + altium-monkey 可导入

#### lcsc_ad_downloader.py — check_dependencies()
- 启动时检查 Node.js、requests、altium-monkey 三项
- Python 包缺失时自动 `pip install`，安装失败则**报错退出**并提示手动安装命令
- Node.js 缺失只报错引导下载（无法自动安装）

#### requirements.txt
- 新增 `altium-monkey>=2026.6.9`

### 关键经验
- **任何依赖缺失都必须有明确的报错信息**——静默跳过是最坏的处理方式，用户完全不知道哪里出了问题
- Node.js `child_process.execFileSync` 的 PATH 解析与交互式 shell 不同，需要通过 `cmd /c` 包装来正确处理 pyenv shim
- OLE 二进制 SchLib/PcbLib 的魔数是 `d0cf11e0a1b11ae1`

## 参考项目

| 项目 | 借鉴内容 |
|------|---------|
| bocang-v1.0-AD-win-x64 | VBScript 插件模式、HTTP 通信、定时器轮询 |
| AD-LCSC-Addons | EasyEDA API 调用方式、搜索 API 格式 |
| JLC2KiCadLib | EasyEDA 图元格式参考（R/E/P/TRACK/PAD 等字段布局） |
| @jlcpcb/mcp (jlc-cli) | LCSC API 参考 |
