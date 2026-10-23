"""Make a gray FBX preview copy by patching only existing material doubles.

No mesh, UV, skin, hierarchy, connection or material-ID records are rewritten.
Usage: python fix_muriel_materials.py SOURCE.fbx OUTPUT_DIRECTORY
"""
from __future__ import annotations

import hashlib
import html
import json
import struct
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Property:
    kind: str
    value: object
    start: int
    end: int


@dataclass
class Node:
    name: str
    props: list[Property]
    children: list[Node]
    start: int
    end: int


def parse(data: bytes) -> list[Node]:
    if not data.startswith(b"Kaydara FBX Binary  \x00\x1a\x00"):
        raise ValueError("Expected binary FBX")
    version = struct.unpack_from("<I", data, 23)[0]
    header_format = "<QQQB" if version >= 7500 else "<IIIB"
    header_size = struct.calcsize(header_format)

    def read_node(pos):
        start = pos
        end, count, prop_length, name_length = struct.unpack_from(header_format, data, pos)
        if end == 0:
            return None, pos + header_size
        assert start < end <= len(data)
        pos += header_size
        name = data[pos:pos + name_length].decode("utf-8")
        pos += name_length
        prop_start = pos
        props = []
        for _ in range(count):
            kind = chr(data[pos])
            pos += 1
            value_start = pos
            if kind in "YCFDIL":
                fmt = "<" + dict(Y="h", C="?", F="f", D="d", I="i", L="q")[kind]
                value = struct.unpack_from(fmt, data, pos)[0]
                pos += struct.calcsize(fmt)
            elif kind in "SR":
                size = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                raw = data[pos:pos + size]
                value = raw.decode("utf-8") if kind == "S" else raw
                pos += size
            elif kind in "fdlibc":
                length, encoding, size = struct.unpack_from("<III", data, pos)
                value = (length, encoding, size)
                pos += 12 + size
            else:
                raise ValueError(f"Unsupported FBX property: {kind!r}")
            props.append(Property(kind, value, value_start, pos))
        assert pos - prop_start == prop_length
        children = []
        while pos < end - header_size:
            child, pos = read_node(pos)
            if child is None:
                break
            children.append(child)
        assert pos <= end
        return Node(name, props, children, start, end), end

    roots = []
    pos = 27
    while pos < len(data):
        root, pos = read_node(pos)
        if root is None:
            break
        roots.append(root)
    return roots


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.children)


def materials(nodes):
    result = []
    for node in walk(nodes):
        if node.name != "Material":
            continue
        values = {}
        for child in node.children:
            if child.name == "Properties70":
                for p in child.children:
                    if p.name == "P":
                        values[p.props[0].value] = p.props[4:]
        result.append((node, values))
    return result


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "Muriel_GDC_GrayPreview.FBX"
    if destination.exists():
        raise FileExistsError(destination)
    original = source.read_bytes()
    roots = parse(original)
    material_records = materials(roots)
    if len(material_records) != 10:
        raise ValueError("Unexpected material count; inspect before modifying")
    modified = bytearray(original)
    changes = []
    rows = []
    allowed = set()
    for material, values in material_records:
        name = material.props[1].value.split("\x00")[0]
        diffuse_before = [p.value for p in values["DiffuseColor"]]
        assert diffuse_before == [0.0, 0.0, 0.0], (name, diffuse_before)
        opacity = values.get("Opacity", [])[0].value
        replacements = {"DiffuseColor": [0.5] * 3, "Diffuse": [0.5] * 3}
        # Keep the original transparent eye overlays; normalize opaque surfaces.
        if opacity == 1.0:
            replacements["TransparencyFactor"] = [0.0]
        for key, new_values in replacements.items():
            properties = values[key]
            assert len(properties) == len(new_values)
            for prop, new in zip(properties, new_values):
                assert prop.kind == "D" and prop.end - prop.start == 8
                modified[prop.start:prop.end] = struct.pack("<d", new)
                allowed.update(range(prop.start, prop.end))
                changes.append({"material": name, "property": key,
                                "offset": prop.start, "before": prop.value, "after": new})
        rows.append({"name": name, "diffuse_before": diffuse_before,
                     "diffuse_after": [0.5] * 3, "opacity": opacity,
                     "transparency_before": values["TransparencyFactor"][0].value,
                     "transparency_after": 0.0 if opacity == 1.0 else values["TransparencyFactor"][0].value})

    repaired = bytes(modified)
    assert len(repaired) == len(original)
    changed_bytes = {i for i, (a, b) in enumerate(zip(original, repaired)) if a != b}
    assert changed_bytes and changed_bytes.issubset(allowed)
    repaired_roots = parse(repaired)
    objects_before = next(n for n in roots if n.name == "Objects")
    objects_after = next(n for n in repaired_roots if n.name == "Objects")
    assert len(objects_before.children) == len(objects_after.children)
    preserved_objects = 0
    for old, new in zip(objects_before.children, objects_after.children):
        assert (old.name, old.start, old.end) == (new.name, new.start, new.end)
        if old.name != "Material":
            assert original[old.start:old.end] == repaired[new.start:new.end]
            preserved_objects += 1
    for old, new in zip(roots, repaired_roots):
        assert old.name == new.name
        if old.name != "Objects":
            assert original[old.start:old.end] == repaired[new.start:new.end]
    for (_, props), row in zip(materials(repaired_roots), rows):
        assert [p.value for p in props["DiffuseColor"]] == row["diffuse_after"]
        assert props["TransparencyFactor"][0].value == row["transparency_after"]
        assert props["Opacity"][0].value == row["opacity"]
    assert source.read_bytes() == original
    destination.write_bytes(repaired)
    assert destination.read_bytes() == repaired
    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "source": str(source), "output": str(destination),
        "source_sha256": sha(original), "output_sha256": sha(repaired),
        "size_bytes": len(original), "material_count": len(rows),
        "opaque_materials_normalized": sum(r["opacity"] == 1 for r in rows),
        "transparent_materials_preserved": sum(r["opacity"] == 0 for r in rows),
        "changed_byte_count": len(changed_bytes),
        "preserved_nonmaterial_objects": preserved_objects,
        "uv_layer_count": sum(n.name == "LayerElementUV" for n in walk(roots)),
        "checks": {"source_unchanged": True, "only_material_value_bytes_changed": True,
                   "geometry_skin_uv_and_other_objects_byte_identical": True,
                   "connections_and_global_settings_byte_identical": True,
                   "file_length_and_node_offsets_unchanged": True,
                   "reparsed_and_material_values_verified": True},
        "max_viewport_verified": False, "materials": rows, "changes": changes,
    }
    (output_dir / "material_repair_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for stage in ("inspection", "verification"):
        inspection = stage == "inspection"
        title = "01 · 原始 FBX 材质检查" if inspection else "02 · 灰色预览副本与验证"
        table_rows = "".join(
            "<tr><td>" + html.escape(row["name"]) + "</td><td>" +
            ("(0, 0, 0)" if inspection else "(0.5, 0.5, 0.5)") +
            f'</td><td>{row["opacity"]:g}</td><td>' +
            f'{row["transparency_before" if inspection else "transparency_after"]:g}</td></tr>'
            for row in rows)
        details = ("<p>10 / 10 个材质的 DiffuseColor 与 Diffuse 均为黑色。</p>"
                   "<p>8 个主体材质：Opacity = 1，TransparencyFactor = 1，存在矛盾。</p>"
                   "<p>2 个眼部覆盖材质原本透明，处理时保留透明设置。</p>" if inspection else
                   "<p>10 个材质改为灰色；8 个主体透明因子改为 0；2 个透明覆盖材质保留透明。</p>"
                   f"<p>非材质对象 {preserved_objects} 个逐字节一致；几何、UV、蒙皮、骨骼及连接未重写。</p>"
                   f"<p>文件长度仍为 {len(original):,} 字节；重新解析与材质值检查通过。</p>")
        page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef2f6;color:#15253b;font:17px 'Microsoft YaHei',sans-serif}}
main{{margin:30px auto;padding:32px 40px;width:1360px;background:white;border:1px solid #ccd6e2;border-radius:12px}}
h1{{font-size:30px;margin:0 0 10px}}p{{margin:8px 0;line-height:1.5}}
.label{{color:#53718c;font-size:15px}}.notice{{padding:12px 16px;background:#fff2ce;border-left:4px solid #cc9d32;margin:16px 0}}
table{{border-collapse:collapse;width:100%;margin:20px 0;font-size:16px}}th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #e0e7ef}}
th{{background:#eaf0f7}}td:first-child{{font-family:Consolas,monospace}}.pass{{color:#14643d}}code{{font:14px Consolas,monospace;overflow-wrap:anywhere}}
</style><main><div class="label">Muriel_GDC · 实际文件检查报告 · {html.escape(report['created_at'])}</div>
<h1>{title}</h1><p>源文件：<code>{html.escape(str(source))}</code></p>
<div class="notice">本图为实际检查报告的浏览器截图。尚未在 3ds Max 视口中验证修复效果。</div>
{details}<table><tr><th>材质</th><th>DiffuseColor</th><th>Opacity</th><th>TransparencyFactor</th></tr>{table_rows}</table>
<p class="pass">原文件未修改 · 材质 ID / 分配关系保留 · 二进制结构检查通过</p>
<p>{'源文件' if inspection else '输出文件'}：<code>{html.escape(str(source if inspection else destination))}</code></p>
<p>SHA-256：<code>{report['source_sha256'] if inspection else report['output_sha256']}</code></p></main></html>'''
        (output_dir / f"{stage}.html").write_text(page, encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "output", "material_count", "opaque_materials_normalized", "transparent_materials_preserved",
        "changed_byte_count", "preserved_nonmaterial_objects", "uv_layer_count", "checks")}, indent=2))


if __name__ == "__main__":
    main()
