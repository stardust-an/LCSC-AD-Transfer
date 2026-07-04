#!/usr/bin/env python3
"""
LCSC-AD-Transfer ASCII-to-Binary Converter
Requires: Python 3.11-3.12, altium-monkey>=2026.6.9
"""

import sys
import re
import argparse
import shutil
from pathlib import Path

import altium_monkey as am
from altium_monkey import (
    AltiumSchLib, SchPointMils, SchRectMils, SchFontSpec,
    ColorValue, LineWidth, LineStyle, PinElectrical, Rotation90,
)
from altium_monkey.altium_pcblib import AltiumPcbLib
from altium_monkey.altium_pcb_enums import (
    PadShape, PcbTextKind, PcbRegionKind, PcbLayer,
)

# ============================================================
# Helpers
# ============================================================

RE_MIL = re.compile(r"^([\d\.\-]+)mil$")


def parse_mil(val):
    if isinstance(val, str):
        m = RE_MIL.match(val.strip())
        if m:
            return float(m.group(1))
        try:
            return float(val)
        except ValueError:
            return 0.0
    return float(val)


def parse_record(line):
    parts = line.strip().split("|")
    result = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            result[k] = v
        elif p:
            result[p] = True
    return result


def decode_widestring(val):
    if not val:
        return ""
    try:
        return "".join(chr(int(c.strip())) for c in val.split(","))
    except:
        return val


def get_color(val_str):
    try:
        return ColorValue(int(val_str))
    except:
        return None


def get_line_width(val_str):
    try:
        v = int(val_str)
        return LineWidth(v) if v <= 3 else v
    except:
        return LineWidth.SMALL


# ============================================================
# SchDoc ASCII → Binary SchLib
# ============================================================

def sch_ascii_to_schlib(ascii_content, title="Component", params=None):
    lines = ascii_content.strip().split("\n")

    # Count pins to determine if this is a basic component (few pins)
    pin_count = sum(1 for l in lines if l.strip().startswith("|RECORD=2|"))
    is_basic = pin_count <= 4  # R/C/L/D/Q etc.

    schlib = AltiumSchLib()
    symbol = schlib.add_symbol(title, description=title)

    # Add component parameters (default NC, override with provided values)
    default_params = {
        "Manufacturer": "NC",
        "MPN": "NC",
        "LCSC": "NC",
        "Price": "NC",
        "Package": "NC",
    }
    if params:
        default_params.update(params)
    y_pos = 0
    for pname, ptext in default_params.items():
        symbol.add_parameter(name=pname, text=str(ptext), x=0, y=y_pos, is_hidden=True)
        y_pos += 50  # stack parameters vertically

    for line in lines:
        l = line.strip()
        if not l or l.startswith("WARNING"):
            continue
        rec = parse_record(l)
        rt = int(rec.get("RECORD", "0"))

        # -- Pin --
        if rt == 2:
            try:
                loc_x = int(float(rec.get("LOCATION.X", "0")))
                loc_y = int(float(rec.get("LOCATION.Y", "0")))
                pin_len = int(float(rec.get("PINLENGTH", "10")))
                conglomerate = int(rec.get("PINCONGLOMERATE", "58"))
                # PINCONGLOMERATE % 4 encodes rotation: 0=0°, 1=270°, 2=180°, 3=90°
                cong_mod = conglomerate % 4
                if cong_mod == 0:
                    rotation = Rotation90.DEG_0    # right
                elif cong_mod == 1:
                    rotation = Rotation90.DEG_90   # up
                elif cong_mod == 2:
                    rotation = Rotation90.DEG_180  # left
                else:
                    rotation = Rotation90.DEG_270  # down
                color_val = int(rec.get("COLOR", "136"))
                pin = am.make_sch_pin(
                    designator=rec.get("DESIGNATOR", ""),
                    name=rec.get("NAME", ""),
                    location_mils=SchPointMils(loc_x * 10, loc_y * 10),
                    length_mils=pin_len * 10,
                    orientation=rotation,
                    electrical_type=PinElectrical.PASSIVE,
                    pin_color=ColorValue(color_val),
                    hidden=rec.get("ISHIDDEN", "F") == "T",
                    name_visible=not is_basic,
                    designator_visible=not is_basic,
                )
                symbol.add_pin(pin)
            except Exception as e:
                print(f"  [WARN] Pin: {e}", file=sys.stderr)

        # -- Line (use convenience method for correct owner_part_id) --
        elif rt == 3:
            try:
                sx = int(float(rec.get("LOCATION.X", "0"))) * 10
                sy = int(float(rec.get("LOCATION.Y", "0"))) * 10
                ex = int(float(rec.get("CORNER.X", "0"))) * 10
                ey = int(float(rec.get("CORNER.Y", "0"))) * 10
                color = int(rec.get("COLOR", "0"))
                lw = get_line_width(rec.get("LINEWIDTH", "1"))
                symbol.add_line(sx, sy, ex, ey, color=color, line_width=lw)
            except Exception as e:
                print(f"  [WARN] Line: {e}", file=sys.stderr)

        # -- Polyline --
        elif rt == 4:
            try:
                n = int(rec.get("LOCATIONCOUNT", "0"))
                pts = [(int(float(rec.get(f"X{i}", "0"))) * 10,
                        int(float(rec.get(f"Y{i}", "0"))) * 10)
                       for i in range(1, n + 1)]
                if pts:
                    symbol.add_polyline(pts,
                        color=int(rec.get("COLOR", "0")),
                        line_width=get_line_width(rec.get("LINEWIDTH", "1")))
            except Exception as e:
                print(f"  [WARN] Polyline: {e}", file=sys.stderr)

        # -- Polygon --
        elif rt == 5:
            try:
                n = int(rec.get("LOCATIONCOUNT", "0"))
                pts = [(int(float(rec.get(f"X{i}", "0"))) * 10,
                        int(float(rec.get(f"Y{i}", "0"))) * 10)
                       for i in range(1, n + 1)]
                if pts:
                    is_solid = rec.get("ISSOLID", "F") == "T"
                    color = int(rec.get("COLOR", "0"))
                    area = int(rec.get("AREACOLOR", str(color)))
                    symbol.add_polygon(pts,
                        color=color,
                        area_color=area if is_solid else 16777215,
                        line_width=get_line_width(rec.get("LINEWIDTH", "3")),
                        is_solid=is_solid)
            except Exception as e:
                print(f"  [WARN] Polygon: {e}", file=sys.stderr)

        # -- Arc or Polyline (RECORD=6 used for BOTH by easyeda2altium) --
        elif rt == 6:
            try:
                # Distinguish: LOCATIONCOUNT → Polyline; RADIUS → Arc
                if rec.get("LOCATIONCOUNT"):
                    n = int(rec.get("LOCATIONCOUNT", "0"))
                    pts = [(int(float(rec.get(f"X{i}", "0"))) * 10,
                            int(float(rec.get(f"Y{i}", "0"))) * 10)
                           for i in range(1, n + 1)]
                    if pts:
                        symbol.add_polyline(pts,
                            color=int(rec.get("COLOR", "0")),
                            line_width=get_line_width(rec.get("LINEWIDTH", "1")))
                else:
                    cx = int(float(rec.get("LOCATION.X", "0"))) * 10
                    cy = int(float(rec.get("LOCATION.Y", "0"))) * 10
                    radius = int(float(rec.get("RADIUS", "0"))) * 10
                    symbol.add_arc(cx, cy, radius,
                        start_angle=float(rec.get("STARTANGLE", "0")),
                        end_angle=float(rec.get("ENDANGLE", "360")),
                        color=int(rec.get("COLOR", "0")),
                        line_width=get_line_width(rec.get("LINEWIDTH", "1")))
            except Exception as e:
                print(f"  [WARN] Arc/Polyline(6): {e}", file=sys.stderr)

        # -- Ellipse --
        elif rt == 8:
            try:
                cx = int(float(rec.get("LOCATION.X", "0"))) * 10
                cy = int(float(rec.get("LOCATION.Y", "0"))) * 10
                rx = int(float(rec.get("RADIUS", "0"))) * 10
                ry = int(float(rec.get("SECONDARYRADIUS", f"{rx // 10}"))) * 10
                color = int(rec.get("COLOR", "0"))
                area = int(rec.get("AREACOLOR", str(color)))
                is_solid = rec.get("ISSOLID", "F") == "T"
                symbol.add_ellipse(cx, cy, rx, ry,
                    color=color,
                    area_color=area if is_solid else 16777215,
                    line_width=get_line_width(rec.get("LINEWIDTH", "1")),
                    is_solid=is_solid)
            except Exception as e:
                print(f"  [WARN] Ellipse: {e}", file=sys.stderr)

        # -- Rounded Rectangle (body) --
        elif rt == 10:
            try:
                x1 = int(float(rec.get("LOCATION.X", "0"))) * 10
                y1 = int(float(rec.get("LOCATION.Y", "0"))) * 10
                x2 = int(float(rec.get("CORNER.X", "0"))) * 10
                y2 = int(float(rec.get("CORNER.Y", "0"))) * 10
                crx = int(float(rec.get("CORNERXRADIUS", "0"))) * 10
                cry = int(float(rec.get("CORNERYRADIUS", "0"))) * 10
                color = int(rec.get("COLOR", "0"))
                # Fill body with light yellow (#FFFFB0 = 0xB0FFFF in Altium BGR),
                # drawn behind pins because RECORD=10 appears before RECORD=2 in ASCII
                symbol.add_rounded_rectangle(x1, y1, x2, y2,
                    corner_x_radius=crx, corner_y_radius=cry,
                    color=color,
                    area_color=0xB0FFFF,
                    line_width=get_line_width(rec.get("LINEWIDTH", "1")),
                    is_solid=True)
            except Exception as e:
                print(f"  [WARN] RoundedRect: {e}", file=sys.stderr)

        # -- Text String --
        elif rt == 11:
            try:
                text = rec.get("TEXT", "")
                if text:
                    x = int(float(rec.get("LOCATION.X", "0"))) * 10
                    y = int(float(rec.get("LOCATION.Y", "0"))) * 10
                    note = am.make_sch_note(
                        bounds_mils=SchRectMils(x, y, x + 200, y + 50),
                        text=text,
                        font=SchFontSpec(name="Verdana", size=9),
                    )
                    symbol.add_object(note)
            except Exception as e:
                print(f"  [WARN] Text: {e}", file=sys.stderr)

        # -- Rectangle --
        elif rt == 13:
            try:
                x1 = int(float(rec.get("LOCATION.X", "0"))) * 10
                y1 = int(float(rec.get("LOCATION.Y", "0"))) * 10
                x2 = int(float(rec.get("CORNER.X", "0"))) * 10
                y2 = int(float(rec.get("CORNER.Y", "0"))) * 10
                color = int(rec.get("COLOR", "0"))
                is_solid = rec.get("ISSOLID", "F") == "T"
                area = int(rec.get("AREACOLOR", str(color if is_solid else 16777215)))
                symbol.add_rectangle(x1, y1, x2, y2,
                    color=color,
                    area_color=area if is_solid else 16777215,
                    line_width=get_line_width(rec.get("LINEWIDTH", "1")),
                    is_solid=is_solid)
            except Exception as e:
                print(f"  [WARN] Rectangle: {e}", file=sys.stderr)

        # -- Skip: Designator(34), Comment(41), Parameter(44) --
        elif rt in (34, 41, 44):
            pass

        # -- Implementation (footprint link) --
        elif rt == 45:
            model_name = rec.get("MODELNAME", "")
            if model_name:
                try:
                    symbol.add_footprint(
                        model_name=model_name,
                        description=rec.get("DESCRIPTION", model_name),
                    )
                except Exception as e:
                    print(f"  [WARN] Impl: {e}", file=sys.stderr)

    return schlib


# ============================================================
# PcbDoc ASCII → Binary PcbLib
# ============================================================

LAYER_MAP = {
    "TOP": PcbLayer.TOP,
    "BOTTOM": PcbLayer.BOTTOM,
    "TOPOVERLAY": PcbLayer.TOP_OVERLAY,
    "BOTTOMOVERLAY": PcbLayer.BOTTOM_OVERLAY,
    "TOPSOLDER": PcbLayer.TOP_SOLDER,
    "BOTTOMSOLDER": PcbLayer.BOTTOM_SOLDER,
    "TOPPASTE": PcbLayer.TOP_PASTE,
    "BOTTOMPASTE": PcbLayer.BOTTOM_PASTE,
    "MULTILAYER": PcbLayer.MULTI_LAYER,
}

PAD_SHAPE_MAP = {
    "ROUND": PadShape.CIRCLE,
    "CIRCLE": PadShape.CIRCLE,
    "RECTANGLE": PadShape.RECTANGLE,
    "OCTAGONAL": PadShape.OCTAGONAL,
    "OVAL": PadShape.ROUNDED_RECTANGLE,
    "ROUNDEDRECTANGLE": PadShape.ROUNDED_RECTANGLE,
}


def map_layer(name):
    return LAYER_MAP.get(name.upper().replace(" ", ""), PcbLayer.TOP)


def map_pad_shape(name):
    return PAD_SHAPE_MAP.get(name.upper().replace(" ", "").replace("_", ""), PadShape.RECTANGLE)


def pcb_ascii_to_pcblib(ascii_content, title="Footprint", step_path=None):
    lines = ascii_content.strip().split("\n")
    pcblib = AltiumPcbLib()
    footprint = pcblib.add_footprint(title, description=title, height="0mil")

    comp_x = 0.0
    comp_y = 0.0

    for line in lines:
        l = line.strip()
        if not l or l.startswith("WARNING"):
            continue
        rec = parse_record(l)
        rt = rec.get("RECORD", "")

        if rt == "Board":
            continue

        elif rt == "Component":
            comp_x = parse_mil(rec.get("X", "0"))
            comp_y = parse_mil(rec.get("Y", "0"))

        elif rt == "Pad":
            try:
                px = parse_mil(rec.get("X", "0")) - comp_x
                py = parse_mil(rec.get("Y", "0")) - comp_y
                footprint.add_pad(
                    designator=rec.get("NAME", ""),
                    position_mils=(px, py),
                    width_mils=parse_mil(rec.get("XSIZE", "0")),
                    height_mils=parse_mil(rec.get("YSIZE", "0")),
                    layer=map_layer(rec.get("LAYER", "TOP")),
                    shape=map_pad_shape(rec.get("SHAPE", "RECTANGLE")),
                    rotation_degrees=float(rec.get("ROTATION", "0")),
                    hole_size_mils=parse_mil(rec.get("HOLEWIDTH", "0")),
                    plated=rec.get("PLATED", "TRUE") == "TRUE",
                )
            except Exception as e:
                print(f"  [WARN] Pad: {e}", file=sys.stderr)

        elif rt == "Track":
            try:
                layer_str = rec.get("LAYER", "TOPOVERLAY")
                if "MECHANICAL" in layer_str.upper() or "KEEPOUT" in layer_str.upper():
                    continue
                footprint.add_track(
                    start_mils=(parse_mil(rec.get("X1", "0")) - comp_x,
                                parse_mil(rec.get("Y1", "0")) - comp_y),
                    end_mils=(parse_mil(rec.get("X2", "0")) - comp_x,
                              parse_mil(rec.get("Y2", "0")) - comp_y),
                    width_mils=parse_mil(rec.get("WIDTH", "5")),
                    layer=map_layer(layer_str),
                )
            except Exception as e:
                print(f"  [WARN] Track: {e}", file=sys.stderr)

        elif rt == "Arc":
            try:
                layer_str = rec.get("LAYER", "TOPOVERLAY")
                if "MECHANICAL" in layer_str.upper() or "KEEPOUT" in layer_str.upper():
                    continue
                footprint.add_arc(
                    center_mils=(parse_mil(rec.get("LOCATION.X", "0")) - comp_x,
                                 parse_mil(rec.get("LOCATION.Y", "0")) - comp_y),
                    radius_mils=parse_mil(rec.get("RADIUS", "0")),
                    start_angle_degrees=float(rec.get("STARTANGLE", "0")),
                    end_angle_degrees=float(rec.get("ENDANGLE", "360")),
                    width_mils=parse_mil(rec.get("WIDTH", "5")),
                    layer=map_layer(layer_str),
                )
            except Exception as e:
                print(f"  [WARN] Arc: {e}", file=sys.stderr)

        elif rt == "Text":
            try:
                layer_str = rec.get("LAYER", "TOPOVERLAY")
                if "MECHANICAL" in layer_str.upper():
                    continue
                # Skip designator/comment — footprint doesn't need name labels
                if rec.get("DESIGNATOR", "False") == "True":
                    continue
                if rec.get("COMMENT", "False") == "True":
                    continue
                text = decode_widestring(rec.get("WIDESTRING", ""))
                if not text:
                    text = rec.get("STRING", "") or rec.get("TEXT", "")
                footprint.add_text(
                    text=text,
                    position_mils=(parse_mil(rec.get("X", "0")) - comp_x,
                                   parse_mil(rec.get("Y", "0")) - comp_y),
                    height_mils=parse_mil(rec.get("HEIGHT", "10")),
                    stroke_width_mils=parse_mil(rec.get("WIDTH", "1")),
                    rotation_degrees=float(rec.get("ROTATION", "0")),
                    layer=map_layer(layer_str),
                    font_name=rec.get("FONTNAME", "Arial"),
                )
            except Exception as e:
                print(f"  [WARN] Text: {e}", file=sys.stderr)

        elif rt == "Region":
            pass

    # Embed 3D STEP model if provided
    if step_path and Path(step_path).exists():
        try:
            step_data = Path(step_path).read_bytes()
            if len(step_data) > 1000:  # sanity check
                model = pcblib.add_embedded_model(
                    name=Path(step_path).name,
                    model_data=step_data,
                )
                footprint.add_embedded_3d_model(model)
                print(f"  [STEP] Embedded: {Path(step_path).name} ({len(step_data)}B)", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] 3D model: {e}", file=sys.stderr)

    return pcblib


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="ASCII-to-Binary Altium Converter")
    parser.add_argument("input", nargs="?", help="Input ASCII file path")
    parser.add_argument("-o", "--output", help="Output binary file path")
    parser.add_argument("--title", default="Component", help="Component/footprint name")
    parser.add_argument("--sch", action="store_true", help="Convert SchDoc → SchLib")
    parser.add_argument("--pcb", action="store_true", help="Convert PcbDoc → PcbLib")
    parser.add_argument("--step", help="Path to STEP 3D model file to embed in PcbLib")
    parser.add_argument("--merge-schlib", help="Cumulative SchLib to merge symbol into")
    parser.add_argument("--merge-pcblib", help="Cumulative PcbLib to merge footprint into")
    parser.add_argument("--lcsc", help="LCSC part number for component parameters")
    parser.add_argument("--pkg", help="Package name for component parameters")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin")
    args = parser.parse_args()

    if not args.sch and not args.pcb:
        args.sch = True

    if args.stdin:
        content = sys.stdin.read()
    elif args.input:
        content = Path(args.input).read_text(encoding="utf-8")
    else:
        print("Error: provide input file or --stdin", file=sys.stderr)
        sys.exit(1)

    if args.pcb:
        result = pcb_ascii_to_pcblib(content, title=args.title, step_path=args.step)
    else:
        sch_params = {}
        if args.lcsc:
            sch_params["LCSC"] = args.lcsc
        if args.pkg:
            sch_params["Package"] = args.pkg
        result = sch_ascii_to_schlib(content, title=args.title, params=sch_params)

    out_path = args.output
    if not out_path:
        ext = ".PcbLib" if args.pcb else ".SchLib"
        out_path = (args.input or "output") + ext if args.input else "output" + ext

    result.save(out_path)
    print(out_path)

    # Merge into cumulative library if requested
    # Strategy: save individual files to components/ dir, rebuild cumulative via merge()
    # Never use AltiumSchLib(filepath=...) to read back — it corrupts binary OLE files!
    if args.sch and args.merge_schlib:
        try:
            merge_path = Path(args.merge_schlib)
            # Save individual component to components dir
            comp_dir = merge_path.parent / "components_sch"
            comp_dir.mkdir(parents=True, exist_ok=True)
            comp_file = comp_dir / (args.title + ".SchLib")
            shutil.copy2(out_path, comp_file)  # overwrites old version if exists

            # Rebuild cumulative from all individual files
            if comp_dir.exists():
                sch_files = list(comp_dir.glob("*.SchLib"))
                if sch_files:
                    merged = AltiumSchLib.merge(
                        input_paths=[str(f) for f in sch_files],
                        output_path=str(merge_path),
                        handle_conflicts="rename",
                        verbose=False,
                    )
                    merged.save(merge_path)  # re-save as binary OLE
            else:
                shutil.copy2(out_path, merge_path)
            print(f"  [Merge] SchLib → {merge_path}", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] SchLib merge failed: {e}", file=sys.stderr)

    if args.pcb and args.merge_pcblib:
        try:
            merge_path = Path(args.merge_pcblib)
            # Save individual footprint to components dir
            comp_dir = merge_path.parent / "components_pcb"
            comp_dir.mkdir(parents=True, exist_ok=True)
            comp_file = comp_dir / (args.title + ".PcbLib")
            shutil.copy2(out_path, comp_file)  # overwrites old version if exists

            # Rebuild cumulative from all individual files
            if comp_dir.exists():
                pcb_files = list(comp_dir.glob("*.PcbLib"))
                cumulative = AltiumPcbLib()
                first = True
                for pf in pcb_files:
                    try:
                        part = AltiumPcbLib.from_file(pf)
                        for fp in part.footprints:
                            cumulative.footprints.append(fp)
                        for k, v in part.models_3d.items():
                            if k not in cumulative.models_3d:
                                cumulative.models_3d[k] = v
                    except Exception:
                        continue
                cumulative.save(merge_path)
            else:
                shutil.copy2(out_path, merge_path)
            print(f"  [Merge] PcbLib → {merge_path}", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] PcbLib merge failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
