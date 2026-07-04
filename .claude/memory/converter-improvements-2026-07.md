---
name: converter-improvements-2026-07
description: 2026-07 转换器核心改进：便利方法统一、引脚朝向四向修复、图形渲染、3D模型绑定、累积库
metadata:
  type: project
---

# 转换器核心改进 (2026-07)

## 便利方法统一 (convenience methods)

**根因**: `am.make_sch_*()` + `symbol.add_object()` 组合无法正确设置 `owner_part_id`（保持 -1），AD 不渲染这些孤儿图形对象。IC 能显示轮廓只因为 RECORD=10 用了 `symbol.add_rounded_rectangle()`。

**修复**: 全部改用 `symbol.add_*()` 便利方法，覆盖所有 RECORD 类型：

| RECORD | 对象 | 之前 | 之后 |
|--------|------|------|------|
| 2 | Pin | `make_sch_pin` + `add_object` | `make_sch_pin` + `add_pin` |
| 3 | Line | `make_sch_line` + `add_object` | `add_line(x1,y1,x2,y2,*)` |
| 4 | Polyline | `make_sch_polyline` + `add_object` | `add_polyline(vertices,*)` |
| 5 | Polygon | `make_sch_polygon` + `add_object` | `add_polygon(vertices,*)` |
| 6 | Arc/Polyline | `make_sch_*` + `add_object` | `add_arc/add_polyline(*)` |
| 8 | Ellipse | `make_sch_ellipse` | `add_ellipse(x,y,rx,ry,*)` |
| 10 | RoundedRect | ✓ 已使用 | `add_rounded_rectangle(x1,y1,x2,y2,*)` |
| 13 | Rectangle | `make_sch_rectangle` + `add_object` | `add_rectangle(x1,y1,x2,y2,*)` |

便利方法正确设置 owner_part_id，所有图形对象（包括简单元件的线条/折线/多边形）在 AD 中可正常渲染。

## RECORD=6 双义解析

easyeda2altium 输出中 RECORD=6 存在二义性：
- 带 `LOCATIONCOUNT` → Polyline（如二极管三角、电阻折线）
- 带 `RADIUS` → Arc（圆弧）

**修复**: 检测字段类型分派到 `add_polyline()` 或 `add_arc()`。之前只按 Arc 处理，坐标解析失败被静默吞掉，导致电阻/电容/二极管无外形。

## 引脚朝向四向修复

**PINCONGLOMERATE 编码规律** (bits 0-1 直接映射 Rotation90 枚举):

| PINCONG | %4 | Rotation90 | 方向 | 引脚位置 |
|---------|-----|------------|------|----------|
| 56 | 0 | DEG_0 | → 右 | 右侧 X=300 |
| 57 | 1 | DEG_90 | ↑ 上 | 底部 Y=300 |
| 58 | 2 | DEG_180 | ← 左 | 左侧 X=50 |
| 59 | 3 | DEG_270 | ↓ 下 | 顶部 Y=50 |

**注意**: PINCONG=57 (%4=1) 和 59 (%4=3) 的上下方向不同于直觉——%4=1 的引脚实际位于底部边缘（Y 大值），需朝上（DEG_90）指向外部；%4=3 引脚位于顶部边缘（Y 小值），需朝下（DEG_270）。

已覆盖所有已知值: 32,34（二极管）, 56,58（STM32）, 56,57,58,59（GD32 四边）。

## 引脚名称隐藏

`pin_count ≤ 4` 的基础元件（R/C/L/D/Q 等）自动隐藏引脚名称和位号：
```python
is_basic = pin_count <= 4
name_visible=not is_basic
designator_visible=not is_basic
```

## IC 轮廓背景填充

RECORD=10 强制 `is_solid=True`，`area_color=0xB0FFFF`（#FFFFB0 浅黄，Altium BGR 编码）。轮廓绘制顺序取决于 ASCII 数据中 RECORD=10 排在 RECORD=2 之前，填充自然在引脚下方。

## PcbLib 丝印清理

跳过 `DESIGNATOR=True` 和 `COMMENT=True` 的 Text record，PcbLib 封装不显示位号/元件名文字。

## 3D 模型自动绑定

流程：下载 STEP → 嵌入 PcbLib → 绑定到封装：
```python
model = pcblib.add_embedded_model(name=step_name, model_data=step_bytes)
footprint.add_embedded_3d_model(model)
```

server.js 中 3D 模型下载移到二进制转换之前，PCB 转换时传 `--step <path>`。

## 累积库 (Cumulative Library)

`%TEMP%\LCSC-AD-Transfer\LCSC-AD-Library.SchLib`
`%TEMP%\LCSC-AD-Transfer\LCSC-AD-Library.PcbLib`

每次搜索新元件自动追加。重复搜索同一元件时覆盖旧版本（非追加）。

**实现方式 (2026-07-04 最终版)**:
- 独立文件保存到 `components_sch/` 和 `components_pcb/` 目录，重复料号直接覆盖
- SchLib 累积库: `AltiumSchLib.merge()` 从目录重建 → JSON 写临时文件 → `save()` 写 OLE → 删临时文件
- PcbLib 累积库: `from_file(first)` 为基底 → 追加其余封装 → `save(tmp)` → `shutil.move(tmp, final)`

**关键 Bug (2026-07-04)**:
1. `AltiumSchLib(filepath=...)` 构造函数会**覆写磁盘文件**（OLE → 被破坏），导致 PlaceSchComponent 拿到无效文件。**严禁**用此构造函数回读刚保存的独立 SchLib。
2. 累积库写入目标文件时遇到 I/O error 32（文件被 AD 锁定），改用临时文件 + 重命名策略。
3. PcbLib 空构造 `AltiumPcbLib()` 不含内部 OLE 结构，`save()` 产出损坏文件。必须用 `from_file()` 加载已有文件为基底。

## SCH 元件参数

每个转换的 SchLib 符号自动添加隐藏参数：
- `Manufacturer` = "NC"
- `MPN` = "NC"
- `LCSC` = 实际料号
- `Price` = "NC"
- `Package` = 实际封装名

使用 `symbol.add_parameter(name, text, x, y, is_hidden=True)` 实现，默认 NC，后续可接入数据源填充。
