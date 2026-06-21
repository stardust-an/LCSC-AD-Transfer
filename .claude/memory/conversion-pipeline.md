---
name: conversion-pipeline
description: EasyEDA API → jsapi.min.js → Altium 格式转换流水线
metadata:
  type: project
---

# 转换流水线

## EasyEDA API

所有 API 端点公开可用，无需登录或 token。

### 获取元件 UUID
```
GET https://easyeda.com/api/products/{lcsc_number}/svgs
Headers: User-Agent (必须，否则被拦截)
Response: { success: true, result: [{ component_uuid: "..." }, ...] }
```
最后 1 个 UUID 是封装（footprint），前面的都是原理图符号（可多个，多部件元件）。

### 获取元件详情
```
GET https://easyeda.com/api/components/{uuid}
Response: {
  result: {
    title: "元件名",
    dataStr: {                    // 原理图符号数据（可能是 JSON 字符串或 dict）
      head: { x, y, c_para: { pre, package, ... } },
      shape: "P~...~...\nR~...~...\n..."  // ~分隔的图元行
    },
    packageDetail: {              // 封装数据
      dataStr: {
        head: { x, y, c_para: { package: "封装名" } },
        shape: "PAD~...~...\nTRACK~...~..."
      }
    }
  }
}
```

**注意**: `dataStr` 有时是 JSON 字符串（需要 `JSON.parse`），有时是已解析的 dict。需要处理两种情况。

### 重要配置
- `trust_env = False` — 必须设置，否则系统代理（如 Clash 127.0.0.1:7897）会导致请求失败
- User-Agent: `Mozilla/5.0 ... Chrome/102.0.0.0 Safari/537.36`
- Timeout: 15 秒

## jsapi.min.js 转换引擎

`converter/jsapi.min.js` (879KB) 是立创 EDA 官方 JSAPI 库。

### 核心函数
```javascript
const lcsc = require("./jsapi.min.js");
const schFile = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
const pcbFile = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDetail.dataStr));
```

返回: 字符串数组（Altium ASCII 5.0 格式的 SchDoc/PcbDoc 文本）。

### 为什么用 jsapi.min.js
- 与立创 EDA 「文件→导出→Altium Designer」使用同一套代码
- 覆盖所有元件类型和边界情况
- 手动解析 EasyEDA 图元（约 20 种图元类型）再通过 AD API 创建库的精度远不如官方引擎
- [[ad-plugin-vbscript-pattern]] 中的早期方案尝试过 Python 解析图元方案，因精度和兼容性问题被替换

### 输出格式
- Altium ASCII 5.0 文本格式
- AD 17/18 可直接打开
- AD 19+ 需通过「文件→导入向导→Altium Designer ASCII」导入

## Python ascii2binary 转换

`converter/ascii2binary.py` 使用 altium-monkey 库进行 ASCII→二进制 OLE 互转。需要 Python 3.11–3.12（3.13+ 不支持）。

**重要 (2026-06-22)**: 二进制输出使用独立路径 `<SchLib>.bin`，避免覆盖 ASCII 回退文件。详见 [[ad-plugin-vbscript-pattern]] 中 PlaceSchComponent 的跨版本兼容性问题。

## ASCII SchLib/PcbLib 生成（JavaScript 端）

server.js 中的 `schDocToSchLib()` 和 `pcbDocToPcbLib()` 在 Node.js 端将 SchDoc/PcbDoc 转为 SchLib/PcbLib ASCII 格式，作为二进制转换失败时的回退。

### schDocToSchLib 关键修复 (2026-06-22)

**问题**: AD24/25 的 SchLib 解析器比 AD26 更严格。原实现只移除了 `LOCATION.X/Y`、`ORIENTATION` 等放置属性，但保留了 `INDEXINSHEET`（图纸索引）——这是 SchDoc 专有属性，在 SchLib 中无效。含有 `INDEXINSHEET` 的 SchLib 在 AD24/25 中会被静默拒绝，库面板显示为空。

**修复**: 在所有记录中移除 SchDoc 专有属性：
- RECORD=1: 移除 `INDEXINSHEET`, `LOCATION.X`, `LOCATION.Y`, `ORIENTATION`, `ISMIRRORED`
- RECORD=31: 移除上述属性 + `SHEETSTYLE`, `SNAPGRIDON` 等图纸设置
- RECORD=34/41/44: 移除 `INDEXINSHEET`

### pcbDocToPcbLib 关键修复 (2026-06-22)

**问题**: 原实现只移除了 Board 记录，但保留了绝对板坐标。PcbLib 中的封装原点应在 (0,0)，所有几何对象使用**相对坐标**。未做坐标归一化导致封装内容偏移到屏幕外。

**修复**: 找到 Component 记录的 X/Y 参考原点，对所有 Pad/Track/Arc/Text/Via/Fill/Region 记录的坐标做 `coord - origin` 偏移。

### fixSchOutput 函数

修复 easyeda2altium 输出的已知问题：
1. 去掉空行（防止双换行导致 AD 解析失败）
2. 只保留第一个 HEADER 行（easyeda2altium 末尾会追加重复 HEADER）
3. RECORD=1 的 DISPLAYMODE 字段可能被设为封装名字符串，AD 期望数字 → 替换为 0
4. 去掉行尾的 `\r\n`（easyeda2altium 自带）

## 备选 API

如果 EasyEDA API 不可用，可降级使用：
```
https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode={lcsc_number}
```

但返回的数据结构不同，需要适配。

## Python 环境检测与依赖报错（server.js）

`server.js` 启动时检测 Python 和 altium-monkey 可用性：

1. `_resolvePython()` 查找 Python 3.11–3.12 可执行文件
2. `import altium_monkey` 验证库是否安装
3. 任一不可用则 `console.error` 红色报错，`HAS_BINARY_CONVERTER = false` 跳过二进制转换

`_resolvePython()` 解析策略：
- **绝对路径** `.exe` → 直接 `execFileSync` 验证版本
- **裸命令**（如 `python312`）→ `cmd /c <cmd> --version` 检测版本（兼容 pyenv shim `.bat`），版本确认后通过 `cmd /c pyenv which <cmd>` 解析为绝对 exe 路径

**设计原则**：任何依赖缺失必须有明确的报错信息——静默跳过是最坏的处理方式，用户完全不知道哪里出了问题。

## 依赖检查（lcsc_ad_downloader.py）

`check_dependencies()` 在 `main()` 启动时运行，检查三项依赖：

| 依赖 | 缺失时行为 |
|------|-----------|
| Node.js 16+ | ❌ 报错引导下载 https://nodejs.org/ → 退出 |
| requests | ⚡ 自动 `pip install` → 失败则报错退出 |
| altium-monkey >=2026.6.9 | ⚡ 自动 `pip install` → 失败则报错退出，提示手动安装命令 |

`_pip_install(python_exe, pkg_name)` 可指定目标 Python 可执行文件安装包。

`requirements.txt` 声明了 `altium-monkey>=2026.6.9` 依赖。
