#!/usr/bin/env python3
"""
LCSC-AD-Transfer — 立创商城元器件批量下载工具
================================================
通过 LCSC 编号批量下载符号 (.SchDoc)、封装 (.PcbDoc) 和 3D 模型 (.step)。

用法:
  python lcsc_ad_downloader.py C8734                          # 单个元件
  python lcsc_ad_downloader.py C8734 C2040 C5446               # 多个元件
  python lcsc_ad_downloader.py --file ids.txt                  # 从文件批量读取
  python lcsc_ad_downloader.py C8734 --output D:\my_lib        # 指定输出目录
  python lcsc_ad_downloader.py C8734 --no-3d                   # 不下载 3D 模型

前置条件:
  需要安装 Node.js 16+ (脚本会自动启动转换服务)
"""

import os
import sys
import json
import time
import argparse
import platform
import subprocess
import urllib.request
from pathlib import Path

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 配置
CONVERTER_URL = "http://localhost:3001"
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
STEP_MODEL_URL = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}"
OBJ_MODEL_URL = "https://modules.easyeda.com/3dmodel/{uuid}"


def check_server():
    """检查转换服务是否在运行"""
    try:
        req = urllib.request.Request(f"{CONVERTER_URL}/")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "running":
                return True
    except Exception:
        pass
    return False


def start_server():
    """尝试自动启动本地转换服务"""
    script_dir = Path(__file__).parent
    converter_dir = script_dir / "converter"
    server_js = converter_dir / "server.js"

    if not server_js.exists():
        print(f"❌ 错误: 未找到 converter/server.js")
        return False

    # 检查 Node.js 是否可用
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print("❌ 错误: Node.js 不可用，请先安装 Node.js 16+")
            return False
        print(f"  Node.js {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ 错误: 未找到 Node.js，请先安装 Node.js 16+")
        print("           下载: https://nodejs.org/")
        return False
    except subprocess.TimeoutExpired:
        print("❌ 错误: Node.js 响应超时")
        return False

    # 检查依赖
    node_modules = converter_dir / "node_modules"
    express_module = converter_dir / "node_modules" / "express"
    if not node_modules.exists() or not express_module.exists():
        print("  安装依赖: npm install...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(converter_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"❌ 错误: npm install 失败")
            if result.stderr:
                print(f"  {result.stderr.strip()[:500]}")
            return False
        print("  依赖安装完成")

    # 启动服务
    print("  启动转换服务...")
    try:
        if platform.system() == "Windows":
            # DETACHED_PROCESS (0x00000008) + CREATE_NO_WINDOW (0x08000000)
            proc = subprocess.Popen(
                ["node", "server.js"],
                cwd=str(converter_dir),
                creationflags=subprocess.DETACHED_PROCESS | 0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                ["node", "server.js"],
                cwd=str(converter_dir),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        print(f"❌ 错误: 无法启动服务进程: {e}")
        return False

    # 等待服务就绪（最多 15 秒）
    for _ in range(15):
        time.sleep(1)
        if check_server():
            print("✓ 转换服务已启动")
            return True

    print("❌ 错误: 服务启动超时 (15s)")
    print("   可能原因: 端口 3001 被占用或依赖缺失")
    print("   手动排查: cd converter && node server.js")
    return False


def fetch_component(lcsc_id):
    """通过 LCSC 编号获取转换后的 SchDoc 和 PcbDoc 内容"""
    url = f"{CONVERTER_URL}/convert/lcsc/{lcsc_id}"
    req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        if not data.get("success"):
            raise RuntimeError(f"转换失败: {data.get('error', 'Unknown error')}")
        return data
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接到转换服务: {e.reason}") from e


def download_3d_model(uuid, output_dir, lcsc_id):
    """下载 3D 模型 (STEP 格式优先)"""
    if not uuid:
        return None

    step_path = output_dir / f"{lcsc_id}.step"

    # 如果已存在则跳过
    if step_path.exists():
        print(f"  [3D] STEP 已存在，跳过: {step_path.name}")
        return str(step_path)

    # 尝试下载 STEP 格式
    step_url = STEP_MODEL_URL.format(uuid=uuid)
    try:
        req = urllib.request.Request(step_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) > 1000:  # 有效文件至少大于 1KB
                step_path.write_bytes(data)
                size_kb = len(data) / 1024
                print(f"  [3D] STEP 下载成功: {step_path.name} ({size_kb:.1f} KB)")
                return str(step_path)
    except Exception as e:
        print(f"  [3D] STEP 下载失败: {e}")

    # 回退到 OBJ 格式
    obj_path = output_dir / f"{lcsc_id}.obj"
    if obj_path.exists():
        print(f"  [3D] OBJ 已存在，跳过: {obj_path.name}")
        return str(obj_path)

    obj_url = OBJ_MODEL_URL.format(uuid=uuid)
    try:
        req = urllib.request.Request(obj_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) > 1000:
                obj_path.write_bytes(data)
                size_kb = len(data) / 1024
                print(f"  [3D] OBJ 下载成功: {obj_path.name} ({size_kb:.1f} KB)")
                return str(obj_path)
    except Exception as e:
        print(f"  [3D] OBJ 下载失败: {e}")

    print(f"  [3D] 警告: 无法获取 3D 模型")
    return None


def save_files(data, output_dir, download_3d=True):
    """保存 SchDoc 和 PcbDoc 文件"""
    comp = data["component"]
    lcsc_id = comp["lcscId"]
    title = comp.get("title", lcsc_id)
    pkg = comp.get("package", "Unknown")

    # 清理文件名中的非法字符
    safe_title = "".join(c if c.isalnum() or c in "._-()[]" else "_" for c in title)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存原理图
    sch_path = output_dir / f"{lcsc_id}_{safe_title}.SchDoc"
    sch_path.write_text(data["sch"], encoding="utf-8")
    print(f"  [SCH] 保存: {sch_path.name}")

    # 保存封装
    pcb_path = output_dir / f"{lcsc_id}_{safe_title}.PcbDoc"
    pcb_path.write_text(data["pcb"], encoding="utf-8")
    print(f"  [PCB] 保存: {pcb_path.name}")

    # 下载 3D 模型
    model3d_path = None
    if download_3d and comp.get("model3dUuid"):
        model3d_path = download_3d_model(comp["model3dUuid"], output_dir, lcsc_id)

    result = {
        "lcsc_id": lcsc_id,
        "title": title,
        "package": pkg,
        "manufacturer": comp.get("manufacturer", ""),
        "sch_path": str(sch_path),
        "pcb_path": str(pcb_path),
        "model3d_path": model3d_path,
    }

    # 如果有警告，记录下来
    if data.get("warnings") and len(data["warnings"]) > 0:
        result["warnings"] = len(data["warnings"])

    return result


def print_summary(results):
    """打印下载摘要"""
    print()
    print("=" * 60)
    print("  下载摘要")
    print("=" * 60)

    ok = [r for r in results if r]
    failed = len(results) - len(ok)

    for r in ok:
        status = "✓"
        details = f"{r['title']} ({r['package']})"
        if r.get("warnings"):
            status = "⚠"
            details += f" [{r['warnings']} warnings]"
        print(f"  {status} {r['lcsc_id']} → {details}")

    if failed:
        print(f"  ✗ {failed} 个失败")

    print()
    print(f"  成功: {len(ok)}/{len(results)}")
    print(f"  输出目录: {args_to_dir()}")
    print("=" * 60)


_args_dir = DEFAULT_OUTPUT


def args_to_dir():
    return _args_dir


def main():
    global _args_dir, CONVERTER_URL

    parser = argparse.ArgumentParser(
        description="LCSC-AD-Transfer — 立创商城元器件批量下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python lcsc_ad_downloader.py C8734
  python lcsc_ad_downloader.py C8734 C2040 C5446
  python lcsc_ad_downloader.py --file ids.txt --output D:\\my_lib
  python lcsc_ad_downloader.py C8734 --no-3d
        """.strip()
    )
    parser.add_argument("ids", nargs="*", help="LCSC 编号列表 (如 C8734 C2040)")
    parser.add_argument("--file", "-f", help="从文件读取 LCSC 编号 (每行一个)")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help=f"输出目录 (默认: {DEFAULT_OUTPUT})")
    parser.add_argument("--no-3d", action="store_true", help="不下载 3D 模型")
    parser.add_argument("--server", default=CONVERTER_URL, help=f"转换服务地址 (默认: {CONVERTER_URL})")

    args = parser.parse_args()
    _args_dir = args.output

    # 更新全局配置
    CONVERTER_URL = args.server

    # 收集 LCSC 编号
    ids = list(args.ids)
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误: 文件不存在: {args.file}")
            sys.exit(1)
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    # 支持逗号、空格、分号分隔
                    for part in stripped.replace(",", " ").replace(";", " ").split():
                        part = part.strip()
                        if part and part not in ids:
                            ids.append(part)

    if not ids:
        print("错误: 请提供至少一个 LCSC 编号")
        parser.print_help()
        sys.exit(1)

    # 去重
    ids = list(dict.fromkeys(ids))

    print(f"LCSC-AD-Transfer — 立创元器件批量下载")
    print(f"  目标数量: {len(ids)}")
    print(f"  输出目录: {args.output}")
    print(f"  3D 模型: {'关闭' if args.no_3d else '开启'}")
    print(f"  转换服务: {CONVERTER_URL}")
    print()

    # 检查服务，未运行时自动启动
    if not check_server():
        print("⚡ 转换服务未运行，正在自动启动...")
        if not start_server():
            print()
            print("   无法自动启动服务，你也可以手动启动:")
            print(f"   cd converter && node server.js")
            sys.exit(1)
    else:
        print("✓ 转换服务已连接")
    print()

    # 逐个下载
    results = []
    for i, lcsc_id in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] {lcsc_id} ", end="", flush=True)
        try:
            data = fetch_component(lcsc_id)
            title = data.get("component", {}).get("title", "?")
            pkg = data.get("component", {}).get("package", "?")
            print(f"→ {title} ({pkg})")

            result = save_files(data, args.output, download_3d=not args.no_3d)
            results.append(result)

        except Exception as e:
            print(f"→ 失败: {e}")
            results.append(None)

        # 适当间隔，避免请求过快
        if i < len(ids):
            time.sleep(0.5)

    print_summary(results)


if __name__ == "__main__":
    main()
