/**
 * LCSC-AD-Transfer 本地转换服务
 *
 * 功能:
 * 1. 接收 LCSC 编号 → 从 EasyEDA API 获取元件数据
 * 2. 调用 JSAPI.easyeda2altium() 转换为 Altium Designer ASCII 格式
 * 3. 返回 .SchDoc / .PcbDoc 文件内容
 *
 * 用法:
 *   node server.js
 *   监听 http://localhost:3001
 */

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFile } = require("child_process");
const { promisify } = require("util");
const execFileAsync = promisify(execFile);

// 加载立创 EDA 官方的 JSAPI 转换库
const lcsc = require("./jsapi.min.js");

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3001;

// Python 3.11 path for altium-monkey binary converter
function _resolvePython(cmd) {
  // If already an absolute path to python.exe, verify and return as-is
  if (path.isAbsolute(cmd) && cmd.endsWith(".exe")) {
    try {
      const result = require("child_process").execFileSync(cmd, ["--version"], { timeout: 5000 });
      const ver = result.toString();
      if (ver.includes("3.11") || ver.includes("3.12")) return cmd;
    } catch (e) { /* fall through */ }
    return null;
  }

  // For bare commands, verify version then resolve to full path via pyenv or where
  try {
    const result = require("child_process").execFileSync("cmd", [
      "/c", cmd + " --version"
    ], { timeout: 5000, windowsHide: true });
    const ver = result.toString();
    if (!ver.includes("3.11") && !ver.includes("3.12")) return null;

    // Try pyenv first (handles shims correctly)
    try {
      const pyenv = require("child_process").execFileSync("cmd", [
        "/c", "pyenv which " + cmd
      ], { timeout: 5000, windowsHide: true });
      const exePath = pyenv.toString().trim();
      if (exePath && fs.existsSync(exePath)) return exePath;
    } catch (e) { /* pyenv not available */ }

    // Fallback: where → prefer .exe
    try {
      const where = require("child_process").execFileSync("cmd", [
        "/c", "where " + cmd
      ], { timeout: 5000, windowsHide: true });
      const lines = where.toString().trim().split(/\r?\n/);
      const exe = lines.find(l => l.toLowerCase().endsWith(".exe"));
      if (exe) return exe.trim();
      const first = lines[0]?.trim();
      if (first) return first;
    } catch (e) { /* where failed */ }

    return cmd; // last resort: bare command
  } catch (e) { /* nope */ }
  return null;
}

const PYTHON311 = (() => {
  const candidates = [
    process.env.PYTHON311,
    "C:\\Users\\L\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
    "C:\\Users\\L\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
    "C:\\Python311\\python.exe",
    "C:\\Python312\\python.exe",
    "python3.12", "python312",
    "python3.11", "python311",
    "python3", "python"
  ];
  for (const c of candidates) {
    if (!c) continue;
    const resolved = _resolvePython(c);
    if (resolved) return resolved;
  }
  return null;
})();
console.log(`[Init] Python (3.11–3.12): ${PYTHON311 || "NOT FOUND (binary conversion disabled)"}`);

// Converter script path
const CONVERTER_SCRIPT = path.join(__dirname, "ascii2binary.py");

// 检查 altium-monkey 是否可用
let ALTIUM_MONKEY_OK = false;
if (PYTHON311 && fs.existsSync(CONVERTER_SCRIPT)) {
  try {
    const checkResult = require("child_process").execFileSync(PYTHON311, [
      "-c", "import altium_monkey; print(altium_monkey.__version__)"
    ], { timeout: 10000 });
    const ver = (checkResult.toString() || "").trim();
    console.log(`[Init] altium-monkey: ${ver}`);
    ALTIUM_MONKEY_OK = true;
  } catch (e) {
    console.error(`[Init] altium-monkey: NOT FOUND — run: pip install altium-monkey>=2026.6.9`);
    console.error(`[Init] Binary SchLib/PcbLib conversion will NOT be available.`);
  }
}

const HAS_BINARY_CONVERTER = PYTHON311 && fs.existsSync(CONVERTER_SCRIPT) && ALTIUM_MONKEY_OK;
console.log(`[Init] Binary converter: ${HAS_BINARY_CONVERTER ? CONVERTER_SCRIPT : "NOT AVAILABLE"}`);

// AD 集成临时输出目录
const AD_TEMP_DIR = path.join(os.tmpdir(), "LCSC-AD-Transfer");
if (!fs.existsSync(AD_TEMP_DIR)) {
  fs.mkdirSync(AD_TEMP_DIR, { recursive: true });
}
console.log(`[Init] AD temp dir: ${AD_TEMP_DIR}`);

// ============================================================
// easyeda2altium 输出修复
// ============================================================

/**
 * 修复 easyeda2altium 输出的已知问题：
 * 1. RECORD=1 的 DISPLAYMODE 字段被设为封装名（字符串），AD 期望数字
 *    导致 OWNERPARTDISPLAYMODE=0 与 DISPLAYMODE 不匹配，引脚被隐藏
 * 2. 行尾自带 \r\n，join 后产生双换行
 */
function fixSchOutput(lines) {
  let headerSeen = false;
  return lines
    .filter(line => line.trim() !== "")            // 去掉空行
    .filter(line => {
      // 只保留第一个 HEADER 行, 过滤后续的重复 HEADER (easyeda2altium 会在末尾
      // 追加 "Icon storage" 和重复的格式头, 导致 AD 解析失败)
      if (line.trim().startsWith("|HEADER=")) {
        if (!headerSeen) { headerSeen = true; return true; }
        return false;
      }
      return true;
    })
    .map(line => {
      // 去掉行尾的 \r\n（easyeda2altium 自带的）
      let cleaned = line.replace(/\r?\n$/, "");
      // 修复 RECORD=1 的 DISPLAYMODE：将非数字值替换为 0
      if (cleaned.startsWith("|RECORD=1|")) {
        cleaned = cleaned.replace(/DISPLAYMODE=[^|]*/, "DISPLAYMODE=0");
      }
      return cleaned;
    });
}

// ============================================================
// API 端点
// ============================================================

/**
 * 健康检查
 */
app.get("/", (req, res) => {
  res.json({
    service: "LCSC-AD-Transfer Converter",
    version: "1.0.0",
    status: "running",
    endpoints: {
      "/convert/lcsc/:id": "通过 LCSC 编号获取并转换",
      "/convert/uuid/:uuid": "通过 EasyEDA UUID 获取并转换",
      "/convert/raw": "POST, 直接转换 raw dataStr"
    }
  });
});

/**
 * 通过 LCSC 编号 (如 C8734) 获取元件数据并转换为 Altium 格式
 */
app.get("/convert/lcsc/:id", async (req, res) => {
  const { id } = req.params;

  try {
    // Step 1: 从 EasyEDA API 获取元件数据
    const url = `https://easyeda.com/api/products/${id}/components?version=6.4.19.5`;
    console.log(`[LCSC] Fetching: ${url}`);

    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
      }
    });

    if (!response.ok) {
      throw new Error(`EasyEDA API returned ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    if (!data.result) {
      throw new Error(`Component ${id} not found in EasyEDA database`);
    }

    // Step 2: 提取关键数据
    const { title, dataStr, packageDetail } = data.result;

    console.log(`[LCSC] Component: ${title}`);
    console.log(`[LCSC] Package: ${dataStr?.head?.c_para?.package || 'N/A'}`);

    // Step 3: 获取 3D 模型 UUID (从 SVGNODE 中提取)
    let model3dUuid = null;
    if (packageDetail?.dataStr?.shape) {
      for (const shape of packageDetail.dataStr.shape) {
        if (shape.startsWith("SVGNODE~")) {
          try {
            const svgNodeStr = shape.substring(8); // 去掉 "SVGNODE~"
            const svgData = JSON.parse(svgNodeStr);
            model3dUuid = svgData.attrs?.uuid;
            console.log(`[LCSC] 3D Model UUID: ${model3dUuid}`);
          } catch (e) {
            // SVGNODE 解析失败，跳过
          }
          break;
        }
      }
    }

    // Step 4: 转换为 Altium 格式
    let schLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
    const pcbLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDetail.dataStr));

    // Step 4.5: 修复 easyeda2altium 的已知 bug
    // Bug 1: RECORD=1 中的 DISPLAYMODE 被设置为封装名（字符串），
    //        但 AD 要求 DISPLAYMODE 为数字。引脚上的 OWNERPARTDISPLAYMODE=0
    //        与 DISPLAYMODE="PDFN-8_..." 不匹配，导致 AD 隐藏部分引脚。
    // Bug 2: 输出行之间有空行，可能导致 AD 解析异常
    schLines = fixSchOutput(schLines);
    let warnings = [];
    for (const line of schLines) {
      if (line.includes("WARNING")) warnings.push(`SCH: ${line}`);
    }
    for (const line of pcbLines) {
      if (line.includes("WARNING")) warnings.push(`PCB: ${line}`);
    }

    console.log(`[LCSC] Converted: SCH=${schLines.length} lines, PCB=${pcbLines.length} lines`);
    if (warnings.length > 0) {
      console.warn(`[LCSC] Warnings: ${warnings.length}`);
    }

    // Step 6: 返回结果
    res.json({
      success: true,
      component: {
        lcscId: id,
        title: title,
        package: dataStr?.head?.c_para?.package || "Unknown",
        manufacturer: dataStr?.head?.c_para?.Manufacturer || dataStr?.head?.c_para?.BOM_Manufacturer || "",
        model3dUuid: model3dUuid
      },
      sch: schLines.join("\r\n"),
      pcb: pcbLines.join("\r\n"),
      warnings: warnings
    });

  } catch (error) {
    console.error(`[LCSC] Error: ${error.message}`);
    res.json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 通过 EasyEDA UUID 获取元件数据并转换
 */
app.get("/convert/uuid/:uuid", async (req, res) => {
  const { uuid } = req.params;

  try {
    const url = `https://lceda.cn/api/components/${uuid}`;
    console.log(`[UUID] Fetching: ${url}`);

    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
      }
    });

    if (!response.ok) {
      throw new Error(`EasyEDA API returned ${response.status}`);
    }

    const data = await response.json();

    if (!data.result) {
      throw new Error(`Component with UUID ${uuid} not found`);
    }

    const { title, dataStr, packageDetail } = data.result;

    let schLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
    const pcbLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDetail.dataStr));
    schLines = fixSchOutput(schLines);

    res.json({
      success: true,
      component: {
        uuid: uuid,
        title: title,
        package: dataStr?.head?.c_para?.package || "Unknown"
      },
      sch: schLines.join("\r\n"),
      pcb: pcbLines.join("\r\n")
    });

  } catch (error) {
    console.error(`[UUID] Error: ${error.message}`);
    res.json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 直接传入 raw dataStr 进行转换 (用于调试或自定义数据)
 * POST body: { title, dataStr, packageDataStr }
 */
app.post("/convert/raw", (req, res) => {
  try {
    const { title, dataStr, packageDataStr } = req.body;

    if (!title || !dataStr || !packageDataStr) {
      return res.json({
        success: false,
        error: "Missing required fields: title, dataStr, packageDataStr"
      });
    }

    let schLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
    const pcbLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDataStr));
    schLines = fixSchOutput(schLines);

    res.json({
      success: true,
      sch: schLines.join("\r\n"),
      pcb: pcbLines.join("\r\n")
    });

  } catch (error) {
    res.json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 批量转换: POST /convert/batch
 * body: { ids: ["C8734", "C2040", ...] }
 */
app.post("/convert/batch", async (req, res) => {
  const { ids } = req.body;

  if (!Array.isArray(ids) || ids.length === 0) {
    return res.json({ success: false, error: "ids must be a non-empty array" });
  }

  const results = [];

  for (const id of ids) {
    try {
      const url = `https://easyeda.com/api/products/${id}/components?version=6.4.19.5`;
      const response = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0",
          "Accept": "application/json"
        }
      });

      if (!response.ok) {
        results.push({ id, success: false, error: `HTTP ${response.status}` });
        continue;
      }

      const data = await response.json();

      if (!data.result) {
        results.push({ id, success: false, error: "Not found" });
        continue;
      }

      const { title, dataStr, packageDetail } = data.result;
      let schLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
      const pcbLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDetail.dataStr));
      schLines = fixSchOutput(schLines);

      results.push({
        id,
        success: true,
        title,
        package: dataStr?.head?.c_para?.package || "Unknown",
        sch: schLines.join("\r\n"),
        pcb: pcbLines.join("\r\n")
      });

      console.log(`[BATCH] ${id}: OK (${title})`);

    } catch (error) {
      results.push({ id, success: false, error: error.message });
      console.error(`[BATCH] ${id}: ERROR - ${error.message}`);
    }
  }

  res.json({ success: true, results });
});

// ============================================================
// AD 集成: 格式转换辅助函数
// ============================================================

/**
 * 从 easyeda2altium 生成的 .SchDoc 内容中提取组件定义，转为 .SchLib 格式
 *
 * 核心差异:
 *   .SchDoc: 原理图文档 → 组件被 PLACED 在图纸上 (有 X/Y/Orientation)
 *   .SchLib: 原理图库   → 组件是 DEFINITION (无位置属性)
 *
 * RECORD=34 (Designator) 和 RECORD=41 (Comment) 在 SchDoc 中是图纸级对象,
 * 在 SchLib 中不需要 (AD 放置时会自动生成).
 */
function schDocToSchLib(schContent, title) {
  const lines = schContent.split(/\r?\n/);
  const result = [];
  let headerReplaced = false;

  for (const line of lines) {
    const l = line.trim();
    if (!l) continue;

    // 跳过 WARNING 行
    if (l.startsWith("WARNING")) continue;

    if (l.startsWith("|HEADER=")) {
      // 仅替换第一个 HEADER, 后续的 HEADER 跳过
      // (easyeda2altium 输出可能包含多个 HEADER, 如内嵌模型)
      if (!headerReplaced) {
        result.push("|HEADER=Protel for Windows - Schematic Library Ascii File Version 5.0|");
        headerReplaced = true;
      }
      continue;
    }

    if (l.startsWith("|RECORD=1|")) {
      // 移除组件放置属性, 保留定义属性
      const parts = l.split("|").filter(Boolean);
      const filtered = parts.filter(p => {
        const key = p.split("=")[0];
        return !["LOCATION.X", "LOCATION.Y", "ORIENTATION", "ISMIRRORED", "WEIGHT"].includes(key);
      });
      result.push("|" + filtered.join("|") + "|");
    } else if (l.startsWith("|RECORD=31|")) {
      // RECORD=31: 文档/库设置 - 移除图纸特有属性
      const parts = l.split("|").filter(Boolean);
      const filtered = parts.filter(p => {
        const key = p.split("=")[0];
        return ![
          "SHEETSTYLE", "SHEETNUMBERSPACESIZE", "BORDERON",
          "CUSTOMX", "CUSTOMY", "USECUSTOMSHEET",
          "CUSTOMXZONES", "CUSTOMYZONES", "CUSTOMMARGINWIDTH",
          "SNAPGRIDON", "VISIBLEGRIDON", "SNAPGRIDSIZE", "VISIBLEGRIDSIZE",
          "HOTSPOTGRIDON", "HOTSPOTGRIDSIZE"
        ].includes(key);
      });
      result.push("|" + filtered.join("|") + "|");
    } else {
      // 保留所有其他记录 (包括 RECORD=34,41,44,45 等)
      // 不再删除任何记录以避免 INDEXINSHEET/OwnerIndex 引用错位
      result.push(l);
    }
  }

  return result.join("\r\n");
}

/**
 * 从 easyeda2altium 生成的 .PcbDoc 内容中提取封装定义，转为 .PcbLib 格式
 *
 * .PcbDoc: PCB 文档 → 封装被 PLACED 在电路板上
 * .PcbLib: PCB 库   → 封装是 DEFINITION
 *
 * 对于 AD ASCII 5.0 PCB 格式, 主要区别在 BOARD 记录.
 * 这里做最小化转换: 保留封装定义部分, 去除 board-level 记录.
 */
function pcbDocToPcbLib(pcbContent, title) {
  const lines = pcbContent.split(/\r?\n/);
  const result = [];
  let skippedBoards = 0;

  for (const line of lines) {
    const l = line.trim();
    if (!l) continue;

    if (l.startsWith("WARNING")) continue;

    // 跳过所有 |RECORD=Board| 记录 (板层叠/坐标系统等)
    // .PcbLib 只需要封装定义 (Pad, Track, Arc, Component 等)
    if (l.startsWith("|RECORD=Board|")) {
      skippedBoards++;
      continue;
    }

    result.push(l);
  }

  console.log(`[pcbDocToPcbLib] Skipped ${skippedBoards} board records, kept ${result.length} footprint records`);
  return result.join("\r\n");
}

// ============================================================
// AD 集成端点: 返回可直接放置的库文件
// ============================================================

/**
 * GET /ad-place/:id
 *
 * 专门为 Altium Designer 脚本设计:
 *   1. 从 EasyEDA 获取 LCSC 元件数据
 *   2. 调用 JSAPI 转换为 Altium ASCII
 *   3. 后处理生成 .SchLib / .PcbLib 格式
 *   4. 保存到临时目录
 *   5. 返回管道分隔的简单格式 (方便 VBScript 解析)
 *
 * 返回格式 (成功):
 *   success|schLibPath|pcbLibPath|title|package|model3dUuid
 *
 * 返回格式 (失败):
 *   error|errorMessage
 */
app.get("/ad-place/:id", async (req, res) => {
  const { id } = req.params;

  try {
    // Step 1: 从 EasyEDA API 获取元件数据
    const url = `https://easyeda.com/api/products/${id}/components?version=6.4.19.5`;
    console.log(`[AD-Place] Fetching: ${url}`);

    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
      }
    });

    if (!response.ok) {
      return res.send(`error|EasyEDA API returned ${response.status}`);
    }

    const data = await response.json();

    if (!data.result) {
      return res.send(`error|Component ${id} not found in EasyEDA database`);
    }

    const { title, dataStr, packageDetail } = data.result;
    const pkg = dataStr?.head?.c_para?.package || "Unknown";
    console.log(`[AD-Place] Component: ${title} (${pkg})`);

    // Step 2: 转换为 Altium 格式
    let schLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(dataStr));
    const pcbLines = lcsc.JSAPI.easyeda2altium(title, JSON.stringify(packageDetail.dataStr));
    schLines = fixSchOutput(schLines);

    const schContent = schLines.join("\r\n");
    const pcbContent = pcbLines.join("\r\n");

    // Step 3: 获取 3D 模型 UUID
    let model3dUuid = "";
    if (packageDetail?.dataStr?.shape) {
      for (const shape of packageDetail.dataStr.shape) {
        if (shape.startsWith("SVGNODE~")) {
          try {
            const svgNodeStr = shape.substring(8);
            const svgData = JSON.parse(svgNodeStr);
            model3dUuid = svgData.attrs?.uuid || "";
          } catch (e) { /* ignore */ }
          break;
        }
      }
    }

    // Step 4: 保存 ASCII SchDoc/PcbDoc 到临时目录
    const safeTitle = title.replace(/[\\/:*?"<>|]/g, "_");
    const schDocPath = path.join(AD_TEMP_DIR, `${id}_${safeTitle}.SchDoc`);
    const pcbDocPath = path.join(AD_TEMP_DIR, `${id}_${safeTitle}.PcbDoc`);
    const schLibPath = path.join(AD_TEMP_DIR, `${id}_${safeTitle}.SchLib`);
    const pcbLibPath = path.join(AD_TEMP_DIR, `${id}_${safeTitle}.PcbLib`);

    fs.writeFileSync(schDocPath, schContent, "utf-8");
    fs.writeFileSync(pcbDocPath, pcbContent, "utf-8");

    // Write ASCII SchLib as fallback (in case binary conversion fails)
    const schLibContent = schDocToSchLib(schContent, title);
    const pcbLibContent = pcbDocToPcbLib(pcbContent, title);
    fs.writeFileSync(schLibPath, schLibContent, "utf-8");
    fs.writeFileSync(pcbLibPath, pcbLibContent, "utf-8");

    console.log(`[AD-Place] ASCII SchDoc=${schContent.length}B, PcbDoc=${pcbContent.length}B`);

    // Step 4.5: 下载 3D 模型 (STEP 格式优先) — 必须在二进制转换之前
    let stepPath = "";
    if (model3dUuid) {
      const stepFile = path.join(AD_TEMP_DIR, `${id}.step`);
      if (fs.existsSync(stepFile)) {
        console.log(`[AD-Place] 3D model already exists: ${stepFile}`);
        stepPath = stepFile;
      } else {
        const stepUrl = `https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/${model3dUuid}`;
        try {
          const stepResp = await fetch(stepUrl, {
            headers: { "User-Agent": "Mozilla/5.0" }
          });
          if (stepResp.ok) {
            const stepData = Buffer.from(await stepResp.arrayBuffer());
            if (stepData.length > 1000) {
              fs.writeFileSync(stepFile, stepData);
              const sizeKb = (stepData.length / 1024).toFixed(1);
              console.log(`[AD-Place] 3D model downloaded: ${stepFile} (${sizeKb} KB)`);
              stepPath = stepFile;
            }
          } else {
            console.log(`[AD-Place] 3D model not available (HTTP ${stepResp.status})`);
          }
        } catch (e) {
          console.log(`[AD-Place] 3D model download failed: ${e.message}`);
        }
      }
    }

    // Cumulative library paths (accumulate all searched components)
    const cumulativeSchLib = path.join(AD_TEMP_DIR, "LCSC-AD-Library.SchLib");
    const cumulativePcbLib = path.join(AD_TEMP_DIR, "LCSC-AD-Library.PcbLib");

    // Step 5: 调用 Python 生成二进制 SchLib/PcbLib (altium-monkey)
    let binSchLibPath = "";
    let binPcbLibPath = "";

    if (HAS_BINARY_CONVERTER) {
      try {
        const { stdout } = await execFileAsync(PYTHON311, [
          CONVERTER_SCRIPT, "--sch", schDocPath,
          "-o", schLibPath, "--title", title,
          "--merge-schlib", cumulativeSchLib
        ], { timeout: 30000 });
        binSchLibPath = (stdout || "").trim();
        if (binSchLibPath && fs.existsSync(binSchLibPath)) {
          console.log(`[AD-Place] Binary SchLib: ${binSchLibPath} (${fs.statSync(binSchLibPath).size}B)`);
        } else {
          binSchLibPath = "";
        }
      } catch (e) {
        console.warn(`[AD-Place] Binary SchLib failed: ${e.message}`);
      }

      try {
        const pcbArgs = [
          CONVERTER_SCRIPT, "--pcb", pcbDocPath,
          "-o", pcbLibPath, "--title", pkg,
          "--merge-pcblib", cumulativePcbLib
        ];
        if (stepPath) pcbArgs.push("--step", stepPath);
        const { stdout } = await execFileAsync(PYTHON311, pcbArgs, { timeout: 30000 });
        binPcbLibPath = (stdout || "").trim();
        if (binPcbLibPath && fs.existsSync(binPcbLibPath)) {
          console.log(`[AD-Place] Binary PcbLib: ${binPcbLibPath} (${fs.statSync(binPcbLibPath).size}B)`);
        } else {
          binPcbLibPath = "";
        }
      } catch (e) {
        console.warn(`[AD-Place] Binary PcbLib failed: ${e.message}`);
      }
    }

    // Step 6: 返回管道分隔格式 (VBScript 易解析)
    // 格式: success|schLibPath|pcbLibPath|schDocPath|pcbDocPath|stepPath|title|package|model3dUuid
    //        |binSchLibPath|binPcbLibPath
    // schLibPath/pcbLibPath: ASCII fallback (SchDoc/PcbDoc header swap)
    // binSchLibPath/binPcbLibPath: true binary OLE files (PlaceSchComponent ready)
    // schDocPath/pcbDocPath: original ASCII SchDoc/PcbDoc (direct open)
    res.send(
      `success|${schLibPath}|${pcbLibPath}|${schDocPath}|${pcbDocPath}|${stepPath}|` +
      `${title}|${pkg}|${model3dUuid}|${binSchLibPath}|${binPcbLibPath}`
    );

  } catch (error) {
    console.error(`[AD-Place] Error: ${error.message}`);
    res.send(`error|${error.message}`);
  }
});

// ============================================================
// 启动服务
// ============================================================
app.listen(PORT, () => {
  console.log(`╔════════════════════════════════════════════════╗`);
  console.log(`║     LCSC-AD-Transfer Converter Service        ║`);
  console.log(`║     本地转换服务已启动                         ║`);
  console.log(`║     http://localhost:${PORT}                     ║`);
  console.log(`╚════════════════════════════════════════════════╝`);
  console.log();
  console.log(`示例: http://localhost:${PORT}/convert/lcsc/C8734`);
});
