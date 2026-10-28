"""Session-only orthographic viewport workaround for Labs Flipbook Textures 1.0.

Run in Houdini's Python Shell after loading the scene. Does not render, change
camera parameters, edit the HDA, or persist into the HIP file. Restart Houdini or
call hou.session.remove_flipbook_ortho_workaround() to remove it.

Designed for a static render camera. Live Houdini render verification is still
required; test one frame before rendering the full atlas.
"""

import functools
import math

import hou


def install(node_path="/out/flipbook_textures1"):
    node = hou.node(node_path)
    if node is None or "flipbook_textures" not in node.type().name():
        raise RuntimeError("Select the correct Labs Flipbook Textures node path.")

    module = node.hdaModule()
    original = getattr(module, "_ortho_workaround_original", None)
    if original is None:
        original = module.setCommonViewportSettings
        module._ortho_workaround_original = original

    @functools.wraps(original)
    def configure_viewport(render_node, scene_viewer, render_type):
        result = original(render_node, scene_viewer, render_type)
        camera = render_node.node(render_node.evalParm("camerapath"))
        if camera is None or camera.evalParm("projection") != "ortho":
            return result

        viewport = result["viewport"]
        # Labs already copies the view transform. Keep it, but explicitly set
        # projection/width on a detached viewport camera rather than depending
        # on orthographic camera-object binding in the floating viewport.
        view_camera = viewport.defaultCamera().stash()
        view_camera.setPerspective(False)
        width = camera.evalParm("orthowidth")
        if width <= 0:
            raise RuntimeError("Camera Ortho Width must be positive.")
        view_camera.setOrthoWidth(width)
        resolution = camera.evalParmTuple("res")
        view_camera.setAspectRatio(
            resolution[0] * camera.evalParm("aspect") / resolution[1]
        )
        view_camera.setClipPlanes(
            (camera.evalParm("near"), camera.evalParm("far"))
        )
        view_camera.setWindowOffset(camera.evalParmTuple("win"))
        view_camera.setWindowSize(camera.evalParmTuple("winsize"))

        # Disconnect before applying settings to avoid writing back to cam1.
        viewport.lockCameraToView(False)
        viewport.useDefaultCamera()
        viewport.setDefaultCamera(view_camera)
        live_camera = viewport.defaultCamera()
        if not live_camera.isOrthographic() or not math.isclose(
            live_camera.orthoWidth(), width, rel_tol=1e-5
        ):
            raise RuntimeError("The floating viewport rejected orthographic settings.")
        print(
            "[Flipbook ortho workaround] {}: orthographic width = {}".format(
                render_node.path(), width
            )
        )
        return result

    module.setCommonViewportSettings = configure_viewport

    def remove():
        saved = getattr(module, "_ortho_workaround_original", None)
        if saved is not None:
            module.setCommonViewportSettings = saved
            del module._ortho_workaround_original
        print("[Flipbook ortho workaround] Removed.")

    hou.session.remove_flipbook_ortho_workaround = remove
    print(
        "[Flipbook ortho workaround] Installed for this Labs asset module in "
        "the current session. Perspective cameras remain unchanged. "
        "Set the camera to Orthographic and test one Final Color frame."
    )


install()
