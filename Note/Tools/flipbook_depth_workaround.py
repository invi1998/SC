"""Session-only Labs Depth replacement for Houdini 22.0.

The legacy OpenGL ROP crashes in DM_RenderVulkan on this machine, including
with a 128px sphere. The new Flipbook ROP with lighting disabled renders
valid Pz for both a sphere and the cached BurnSomke smoke.

Installation does not render, save the HIP, or alter the installed Labs HDA.
Use the Labs Render Depth button afterwards. Restarting Houdini removes the
override. All other Labs passes and its depth remapping/packing stay intact.
The requested frame count must equal the number of atlas tiles.
"""

import math
import os
import tempfile

import hou


def _render_modern_depth(node, namespace, single_pass=True):
    if node.evalParm("renderer_d") == 0:
        return True
    if namespace["checkInputs"](node) is None:
        raise RuntimeError("Labs camera or Pyro Bake Volume input is invalid.")

    start, end, step = [float(node.evalParm(p)) for p in ("f1", "f2", "f3")]
    if step <= 0 or end < start:
        raise ValueError("Depth requires an increasing frame range and positive increment.")
    count = int(math.floor((end - start) / step + 1e-6)) + 1
    # Labs' old ROP maps gridsizex to rows and gridsizey to columns.
    rows, columns = [int(node.evalParm(p)) for p in ("gridsizex", "gridsizey")]
    if count != rows * columns:
        raise ValueError(
            "Depth frame count ({}) must equal atlas rows x columns ({}). "
            "Adjust Start/End/Inc or Columns/Rows before rendering.".format(
                count, rows * columns
            )
        )

    legacy = node.node("opengl_depth")
    scene = node.node("depth")
    if legacy is None or scene is None:
        raise RuntimeError("This Labs asset has a different internal Depth network.")
    destination = os.path.abspath(node.evalParm("img_d"))
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    driver = None
    comp = None
    try:
        driver = hou.node("/out").createNode("flipbook", "codex_depth_modern")
        driver.setParms({
            "camera": node.evalParm("camerapath"),
            "scenepath": scene.path(),
            "sopsource": legacy.evalParm("sopsource"),
            "vobjects": "",
            "forceobjects": "geo",
            "alights": "",
            "excludelights": "*",
            "tres": 1,
            "res1": int(node.evalParm("frameresx")),
            "res2": int(node.evalParm("frameresy")),
            "imagetype": "zdepth",
            "colorcorrect": "none",
            "useraytrace": 0,
            "lighting": "off",
            "aamode": "off",
            "usetextures": 0,
            "displacement": 0,
            "transparency": "high",
            "volumequality": "high",
            "tex3dlimit": "specify",
            "tex3dres": int(legacy.evalParm("tex3dres")),
        })

        with tempfile.TemporaryDirectory(
            prefix="codex_depth_", dir=os.path.dirname(destination)
        ) as scratch:
            # The new ROP's Texture Sheet mode is separate from Depth Image.
            # Render Pz frames, then assemble them using a CPU COP2 mosaic.
            for index in range(count):
                frame = start + index * step
                output = os.path.join(scratch, "D.{:04d}.pic.gz".format(index + 1))
                driver.parm("picture").set(output.replace("\\", "/"))
                print("Modern Depth: tile {}/{}; frame {:g}".format(
                    index + 1, count, frame
                ), flush=True)
                driver.render(frame_range=(frame, frame), ignore_inputs=True)
                if not os.path.isfile(output):
                    raise RuntimeError("Depth image was not written: " + output)

            comp = hou.node("/img").createNode("img", "codex_depth_atlas")
            reader = comp.createNode("file", "read_Pz_frames")
            reader.setParms({
                "filename1": os.path.join(scratch, "D.$F4.pic.gz").replace("\\", "/"),
                "singleimage": 0,
                "start": 1,
                "startframe": 1,
                "length": count,
                "colorspace": "linear",
                "depth": "float32",
            })
            mosaic = comp.createNode("mosaic", "depth_tiles")
            mosaic.setInput(0, reader)
            mosaic.setParms({
                "numperline": columns,
                "stackvert": "ttob",
                "stackhorz": "ltor",
                "stackrows": 1,
                "limitperframe": 1,
                "imagelimit": count,
            })
            expected = (
                int(node.evalParm("frameresx")) * columns,
                int(node.evalParm("frameresy")) * rows,
            )
            actual = (mosaic.xRes(), mosaic.yRes())
            if actual != expected or "Pz" not in mosaic.planes():
                raise RuntimeError("Invalid depth atlas: {} {}; expected {} with Pz".format(
                    actual, mosaic.planes(), expected
                ))
            staged = os.path.join(scratch, "atlas.pic.gz")
            mosaic.saveImage(staged, (1, 1))
            # Keep any existing atlas until every frame and the mosaic succeed.
            os.replace(staged, destination)

        source = node.node("comp_depth/msg_depth")
        if source:
            source.cook(force=True)
        namespace["updateTimeStamp"](node, "lb_timestamp_d")
        print("Modern Depth complete: " + destination, flush=True)
        return True
    finally:
        if comp is not None:
            comp.destroy()
        if driver is not None:
            driver.destroy()


def install_depth_workaround(rop_path="/out/flipbook_textures1"):
    node = hou.node(rop_path)
    if node is None or node.node("opengl_depth") is None:
        raise RuntimeError("Cannot find the Labs Flipbook Textures Depth network.")
    # renderAll remains the original HDA function even after renderDepth is
    # replaced with a function defined in this external module.
    namespace = node.hdaModule().renderAll.__globals__
    key = "_codex_modern_depth_routing"
    state = namespace.get(key)
    if state is None:
        state = {"original": namespace["renderDepth"], "paths": set()}

        def routed_depth(current, single_pass=True):
            if current.path() in state["paths"]:
                return _render_modern_depth(current, namespace, single_pass)
            return state["original"](current, single_pass)

        namespace[key] = state
        namespace["renderDepth"] = routed_depth
    state["paths"].add(node.path())
    print("Installed session-only Modern Depth for " + node.path())
    print("Enable Render Depth, then click that pass's render button.")
    print("Its menu still says OpenGL ROP; the session override uses Flipbook ROP.")
    print("No rendering or HIP saving has started.")


def remove_depth_workaround(rop_path="/out/flipbook_textures1"):
    node = hou.node(rop_path)
    if node is None:
        raise RuntimeError("Cannot find the Labs ROP.")
    namespace = node.hdaModule().renderAll.__globals__
    key = "_codex_modern_depth_routing"
    state = namespace.get(key)
    if state:
        state["paths"].discard(node.path())
        if not state["paths"]:
            namespace["renderDepth"] = state["original"]
            del namespace[key]
    print("Removed Modern Depth override for " + rop_path)
