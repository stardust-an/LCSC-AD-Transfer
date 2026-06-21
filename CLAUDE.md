# LCSC-AD-Transfer 项目约定

## 项目简介
输入 LCSC 料号，一键获取 Altium Designer 原理图符号、PCB 封装和 3D 模型。

## 技术栈
- Python 3.8+（核心下载逻辑）
- Node.js 16+（转换服务 converter/）
- VBScript（AD 插件 AD-Plugin/）

## 项目结构
- `lcsc_ad_downloader.py` — 主下载器
- `converter/` — Node.js 转换服务（将 LCSC 数据转为 AD 格式）
- `AD-Plugin/` — Altium Designer 集成插件
- `output/` — 输出目录（不提交 git）
- `start_server.bat` / `start_server.sh` — 启动本地转换服务

## 约定
- 优先使用原生 API，避免引入不必要的依赖
- 代码修改前先说明思路，不要直接给出代码
- 有多种实现方案时，列出选项让用户选择
- 文档使用简体中文

## 记忆索引
详细记录存放在 `.claude/memory/` 目录下，需要时按路径查阅：
- [架构概览](.claude/memory/architecture-overview.md) — Node.js 转换服务 + VBScript AD 插件架构
- [AD 插件 VBScript 模式](.claude/memory/ad-plugin-vbscript-pattern.md) — 为什么用 VBScript、运行方式、API 参考
- [转换流水线](.claude/memory/conversion-pipeline.md) — EasyEDA API → jsapi.min.js → Altium 格式
- [开发历程 2026-06](.claude/memory/dev-history-2026-06.md) — 方案演进和关键决策
