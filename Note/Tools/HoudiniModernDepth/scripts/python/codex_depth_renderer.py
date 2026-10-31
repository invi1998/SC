"""Verified renderer used by the automatic Modern Depth package."""

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
