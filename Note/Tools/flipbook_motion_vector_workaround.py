"""Route one Labs Motion Vector pass through an already verified SOP branch.

Run in Houdini's Python Shell. Installation does not start a render or save
the scene. The override lasts for this Houdini session only. Other passes
continue using the original Labs network. Intended for this smoke-only setup.
The user verified the viewport branch, the routed Motion Vector atlas render,
and the re-exported MVN RG data in Unreal. Material interpolation accuracy is
not yet validated. See section 25 of ../特效贴图制作.md for the full workflow.
"""

import hou


def install_motion_vector_workaround(
    rop_path="/out/flipbook_textures1",
    source_path="/obj/geo1/attribwrangle1",
):
    rop = hou.node(rop_path)
    source = hou.node(source_path)
    if rop is None or source is None:
        raise RuntimeError("Cannot find the Labs ROP or verified motion-vector SOP.")
    if source.type().category() != hou.sopNodeTypeCategory():
        raise RuntimeError("Motion-vector source must be a SOP node.")
    expected = rop.node("motion_vector/geo/RENDER_MV")
    if expected is None:
        raise RuntimeError("This Labs asset has a different Motion Vector network.")

    module = rop.hdaModule()
    # HDAModule is a proxy: ordinary setattr may only affect that proxy.
    # Change the Python functions' shared namespace used by renderMotionVector.
    namespace = module.renderMotionVector.__globals__
    state_name = "_codex_motion_vector_routing"
    state = namespace.get(state_name)
    if state is None:
        original = namespace["setCommonSceneViewerSettings"]
        state = {"original": original, "routes": {}}

        def routed_settings(node, scene_viewer_node, padding=0):
            route = state["routes"].get(node.path())
            if route and scene_viewer_node.path() == route["expected"]:
                verified_source = hou.node(route["source"])
                if verified_source is None:
                    raise RuntimeError("The verified Motion Vector SOP was removed or renamed.")
                print("Motion Vector source: " + verified_source.path())
                return original(node, verified_source, padding)
            return original(node, scene_viewer_node, padding)

        state["wrapper"] = routed_settings
        namespace["setCommonSceneViewerSettings"] = routed_settings
        namespace[state_name] = state

    state["routes"][rop.path()] = {
        "expected": expected.path(),
        "source": source.path(),
    }
    print("Installed session-only Motion Vector routing for " + rop.path())
    print("Render Motion Vector, check the result, then export Tex 5.")
    print("No render has been started. Keep Depth set to Skip This Pass.")


def remove_motion_vector_workaround(rop_path="/out/flipbook_textures1"):
    rop = hou.node(rop_path)
    if rop is None:
        raise RuntimeError("Cannot find the Labs ROP.")
    module = rop.hdaModule()
    namespace = module.renderMotionVector.__globals__
    state_name = "_codex_motion_vector_routing"
    state = namespace.get(state_name)
    if state is None:
        return
    state["routes"].pop(rop.path(), None)
    if not state["routes"]:
        if namespace["setCommonSceneViewerSettings"] is state["wrapper"]:
            namespace["setCommonSceneViewerSettings"] = state["original"]
        del namespace[state_name]
    print("Removed Motion Vector routing for " + rop.path())


install_motion_vector_workaround()
