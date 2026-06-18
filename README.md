# LCSC-AD-Transfer

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/node-16+-green.svg)](https://nodejs.org/)

> 输入 LCSC 料号，一键获取 Altium Designer 原理图符号、PCB 封装和 3D 模型。

---

## 目录

- [快速开始](#快速开始)
- [AD 集成模式（推荐）](#ad-集成模式推荐)
- [CLI 命令行模式](#cli-命令行模式)
- [输出文件说明](#输出文件说明)
- [工作原理](#工作原理)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [依赖与致谢](#依赖与致谢)
- [免责声明](#免责声明)

---

## 快速开始

### 方式一：AD 集成（推荐）

直接在 Altium Designer 中打开元器件，复制粘贴到原理图：

```bash
# AD 中运行 lcsc_place.vbs 即可，脚本会自动启动后台服务。
# 无需手动运行 start_server.bat。
```

1. Altium Designer 中：`文件` → `运行脚本...` → 选择 `lcsc_place.vbs`
2. 输入 LCSC 料号，如 `C8734`
3. 原理图 + PCB 封装自动在 AD 中打开为标签页
4. 在标签页中 `Ctrl+C`，切到原理图 `Ctrl+V`，点击放置

### 方式二：CLI 下载

保存文件到本地，稍后使用：

```bash
# 安装依赖
pip install -r requirements.txt
cd converter && npm install && cd ..

# 下载元器件
python lcsc_ad_downloader.py C8734

# 文件保存在 output/ 目录下
```

---

## AD 集成模式（推荐）

### 工作流程

```
在 AD 中输入 "C8734"
         |
         v
lcsc_place.vbs  ──自动检测并启动后台服务──>  localhost:3001/ad-place/C8734
         |                                            |
         |                                     server.js:
         |                                       - 调用 easyeda.com API
         |                                       - JSAPI easyeda2altium() 转换
         |                                       - 保存 .SchDoc + .PcbDoc 到 %TEMP%
         |                                       - 返回文件路径
         |
         v
AD 打开 .SchDoc 标签页  +  .PcbDoc 标签页
         |
  [用户: Ctrl+C 复制 → 切到原理图 → Ctrl+V 粘贴 → 点击放置]
```

### 使用步骤

| 步骤 | 操作 |
|------|------|
| 1 | AD 中：`文件` → `运行脚本...` → 选择 `lcsc_place.vbs` |
| 2 | 输入 LCSC 料号，如 `C8734` 或 `C8734, C2040, C5446` |
| 3 | 脚本自动检测并启动后台转换服务 |
| 4 | 每个元器件的 SchDoc + PcbDoc 作为标签页在 AD 中打开 |
| 5 | 在标签页中 `Ctrl+C`，切换到原理图 `Ctrl+V`，点击放置 |

> **注意**：如果项目目录不是 `D:\Download\LCSC-AD-Transfer`，请编辑 `lcsc_place.vbs` 顶部的 `PROJECT_DIR` 常量。

### 转换服务 API

后台 Node.js 服务提供以下接口：

| 接口 | 说明 |
|------|------|
| `GET /` | 健康检查 |
| `GET /convert/lcsc/:id` | 按 LCSC 料号转换，返回 JSON（含 SchDoc/PcbDoc 文本） |
| `GET /convert/uuid/:uuid` | 按 EasyEDA UUID 转换 |
| `POST /convert/raw` | 直接传入 dataStr 转换 |
| `POST /convert/batch` | 批量转换 |
| `GET /ad-place/:id` | **AD 集成专用**：保存文件到 `%TEMP%\LCSC-AD-Transfer\`，返回管道分隔路径 |

`/ad-place/:id` 返回格式：
```
success|SchLib路径|PcbLib路径|SchDoc路径|PcbDoc路径|元件名|封装名|3DUUID
```

---

## CLI 命令行模式

### 命令参数

```
python lcsc_ad_downloader.py [LCSC料号...] [选项]

位置参数:
  LCSC料号              一个或多个 LCSC 元器件编号（如 C8734 C2040）

可选参数:
  -f, --file FILE       从文本文件读取 LCSC 编号（每行一个，支持 # 注释）
  -o, --output DIR      指定输出目录（默认: ./output）
  --no-3d               不下载 3D 模型
  --server URL          指定转换服务地址（默认: http://localhost:3001）
  -h, --help            查看帮助
```

### 使用示例

```bash
# 单个元器件
python lcsc_ad_downloader.py C8734

# 多个元器件
python lcsc_ad_downloader.py C8734 C2040 C5446

# 从 BOM 文件批量下载
python lcsc_ad_downloader.py --file bom.txt --output D:\PCB\MyLibrary

# 不下载 3D 模型
python lcsc_ad_downloader.py C8734 --no-3d

# 使用远程转换服务
python lcsc_ad_downloader.py C8734 --server http://192.168.1.100:3001
```

### BOM 文件格式

```
# 项目 BOM 清单
C8734      # STM32F103C8T6
C2040      # RP2040
C5446      # XC6206P332MR
C7543846   # STC8H8K64U
```

支持逗号、空格、分号分隔。`#` 开头的行为注释。

---

## 输出文件说明

每个元器件在 `%TEMP%\LCSC-AD-Transfer\`（AD 模式）或 `output/`（CLI 模式）下生成：

| 文件 | 格式 | 说明 |
|------|------|------|
| `{料号}_{型号}.SchDoc` | Altium ASCII 5.0 | 原理图符号 |
| `{料号}_{型号}.PcbDoc` | Altium ASCII 5.0 | PCB 封装 |
| `{料号}.step` | STEP 3D | 3D 模型（CLI 模式默认下载） |

### 导入 Altium Designer 的方法

**AD17 / AD18（推荐）：**

1. `文件` → `打开` → 直接打开 `.SchDoc` / `.PcbDoc`
2. 选中元件 → 右键 → `复制`
3. 打开自己的原理图库 / 封装库 → `粘贴`

**AD19 及以上：**

1. `文件` → `导入向导`
2. 选择 `Altium Designer ASCII Schematic/PCB`
3. 按向导完成导入

**3D 模型：**

1. 打开 PCB 封装库
2. `放置` → `3D 元件体` → `Generic STEP Model`
3. 嵌入或链接 `.step` 文件

---

## 工作原理

```
LCSC 料号 (如 C8734)
         |
         v
  easyeda.com/api/products/{id}/components
         |
    元器件数据 (dataStr + packageDetail)
         |
         v
  jsapi.min.js (立创 EDA 官方 JSAPI)
  easyeda2altium() → Altium ASCII 5.0 格式
         |
         v
  .SchDoc (原理图) + .PcbDoc (封装) + .step (3D模型)
```

- **无需登录** — EasyEDA 元器件 API 完全公开
- **本地转换** — 数据不经过任何第三方服务器
- **官方引擎** — `jsapi.min.js` 与立创 EDA "文件 → 导出 → Altium Designer" 使用的是同一套代码

---

## 项目结构

```
LCSC-AD-Transfer/
├── README.md                    # 本说明文档
├── LICENSE                      # MIT 许可证
├── requirements.txt             # Python 依赖 (requests)
├── lcsc_ad_downloader.py        # Python CLI 下载工具
├── lcsc_place.vbs               # Altium Designer 集成脚本
├── start_server.bat             # Windows 启动脚本
├── start_server.sh              # Linux/macOS 启动脚本
├── converter/                   # Node.js 转换服务
│   ├── server.js                # Express API 服务
│   ├── jsapi.min.js             # 立创 EDA 官方 JSAPI 转换库
│   └── package.json             # Node 依赖 (express, cors)
├── output/                      # CLI 下载输出目录
└── 参考项目/                     # 开发参考资料（不参与运行）
    ├── jlc-cli/                 # KiCad 方向参考
    ├── AD-LCSC-Addons/          # AD 插件参考
    └── bocang-v1.0-AD-win-x64/  # 国创库 AD 插件参考
```

---

## 常见问题

### 与 easyeda2kicad 有什么区别？

`easyeda2kicad` 输出 **KiCad** 格式。本工具输出 **Altium Designer** 格式（.SchDoc / .PcbDoc / .step），面向 AD 用户。

### 需要立创 EDA 账号吗？

不需要。EasyEDA API 是公开的，无需登录或 token。

### 为什么 AD19+ 不能直接打开 .SchDoc？

AD19 起要求通过导入向导导入 ASCII 格式文件。使用 `文件` → `导入向导` → `Altium Designer ASCII`。

### 为什么不自动放置元器件，而是打开文件手动复制？

Altium Designer 的脚本 API (`PlaceSchComponent`) 要求二进制格式的库文件。立创的转换引擎输出的是 ASCII 格式。通过剪贴板（打开文件 → Ctrl+C/V）是最可靠、兼容所有 AD 版本的方案。

### 3D 模型下载失败怎么办？

部分元器件可能没有 3D 模型。确认网络连接正常后重试，或使用 `--no-3d` 跳过。

### 转换的符号/封装准确吗？

使用的是立创 EDA 官方转换引擎 (`jsapi.min.js`)。但转换结果不保证 100% 完整，导入后请务必检查：
- 引脚编号是否匹配
- 焊盘尺寸是否合适
- 丝印是否完整

### 支持批量下载多少？

没有硬性限制。建议一次不超过 50 个，避免请求过于密集。

### 转换服务端口被占用？

```bash
# Windows PowerShell
taskkill /F /IM node.exe

# 或者使用其他端口
$env:PORT=3002; node converter/server.js
# 运行时指定：python lcsc_ad_downloader.py C8734 --server http://localhost:3002
```

---

## 兼容性说明

| Altium Designer 版本 | 支持情况 | 导入方式 |
|---------------------|---------|---------|
| AD 17 及以下 | 完全支持 | 直接打开 |
| AD 18 | 完全支持 | 直接打开 |
| AD 19 ~ AD 25 | 需额外步骤 | 文件 → 导入向导 |

导出格式为 **Altium ASCII 5.0**（与立创 EDA 官网导出格式一致）。

**注意事项：**
- 生成的文件并非 100% 完整，导入后请仔细检查
- 部分复杂封装的丝印层可能需要手动调整
- 3D 模型的定位可能需要微调

---

## 依赖与致谢

| 组件 | 来源 | 说明 |
|------|------|------|
| `jsapi.min.js` | 立创 EDA 官方 JSAPI | EasyEDA → Altium 格式转换引擎 |
| EasyEDA API | `easyeda.com/api` | 元器件数据公开接口 |
| AD-LCSC-Addons | [TimonPeng/AD-LCSC-Addons](https://github.com/TimonPeng/AD-LCSC-Addons) | 架构参考（Altium Designer 插件） |
| jlc-cli | [l3wi/jlc-cli](https://github.com/l3wi/jlc-cli) | API 接口参考（KiCad 方向） |

致谢：
- 立创商城 / 立创 EDA 提供公开元器件数据和转换库
- Altium Designer 提供稳定的 ASCII 文件格式规范
- 国创库 AD 插件提供 AD 脚本集成参考

---

## 免责声明

1. **本工具为社区维护项目，与立创商城、立创 EDA、嘉立创无任何官方关联。**
2. 生成的 Altium Designer 文件由立创 EDA 的 `easyeda2altium` 引擎自动转换，**不保证 100% 完整准确**，请在导入后仔细检查符号引脚和封装尺寸。
3. 作者不承担因库文件错误导致的任何设计损失，使用前请自行验证。
4. 使用 EasyEDA 公开 API 时请遵守其服务条款，请勿用于大规模商业爬取。

---

## License

MIT License. 详见 [LICENSE](LICENSE) 文件。

---

> 提示：如果这个项目对你有帮助，请给个 Star 让更多人看到！
