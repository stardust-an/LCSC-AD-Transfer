---
name: architecture-overview
description: 项目整体架构：Node.js 转换服务 + VBScript AD 插件
metadata:
  type: project
---

# LCSC-AD-Transfer 架构概览

## 架构

```
用户输入 LCSC 料号 (如 C8734)
         |
         v
AD-Plugin/lcsc_place.vbs  ──── 自动检测/启动 ────>  converter/server.js (localhost:3001)
         |                                                  |
         |                                     EasyEDA API ← easyeda.com/api
         |                                     jsapi.min.js: easyeda2altium()
         |                                     输出 Altium ASCII 5.0 格式
         |                                     .SchDoc + .PcbDoc 文本
         |
         v
AD 打开 SchDoc + PcbDoc 标签页
用户 Ctrl+C/V 复制到自己的原理图/PCB
```

## 组件

| 组件 | 技术 | 职责 |
|------|------|------|
| converter/server.js | Node.js + Express | HTTP API、EasyEDA 数据获取、格式转换 |
| converter/jsapi.min.js | 立创 EDA 官方 JSAPI | `easyeda2altium()` 核心转换引擎（879KB） |
| converter/ascii2binary.py | Python 3.11–3.12 (altium-monkey) | ASCII 格式→二进制 OLE 格式互转 |
| AD-Plugin/lcsc_place.vbs | VBScript | AD 插件：InputBox 输入、调用 API、打开文件 |
| AD-Plugin/LCSC-AD-Transfer.PrjScr | AD 脚本项目 | 注册到 AD 工具栏/菜单 |
| lcsc_ad_downloader.py | Python CLI | 批量下载，供命令行使用；启动时检查依赖（Node.js/requests/altium-monkey） |
| start_server.bat | Windows 批处理 | 启动 Node.js 转换服务 |

**Why:** 采用 jsapi.min.js 官方转换引擎而非手动解析 EasyEDA 图元，因为该引擎经过立创 EDA 官方验证，覆盖所有元件类型和边界情况，避免自行实现带来的精度风险。

**How to apply:** 修改转换逻辑时只改 server.js，不改 jsapi.min.js；AD 集成修改只改 lcsc_place.vbs。
