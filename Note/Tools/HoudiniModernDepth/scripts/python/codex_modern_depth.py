"""Automatically route all original Labs Depth buttons to a verified renderer.

Loaded by this package's ready.py. Does not modify the installed Labs HDA,
save scenes, simulate, or render on startup. The patch covers future nodes
of the same type, and is rechecked after scene loads and library changes.
"""

from datetime import datetime
from pathlib import Path
import traceback

import hou
from codex_depth_renderer import _render_modern_depth


_TYPE = "labs::flipbook_textures::1.0"
_KEY = "_codex_global_modern_depth"
_enabled = False
_registered = False


def _log(message):
    try:
        target = Path(__file__).resolve().parents[2] / "startup.log"
        with target.open("a", encoding="utf-8") as stream:
            stream.write("{} {}\n".format(datetime.now().isoformat(timespec="seconds"), message))
    except OSError:
        pass


def _namespace():
    node_type = hou.nodeType(hou.ropNodeTypeCategory(), _TYPE)
    if node_type is None:
        return None
    module = node_type.hdaModule()
    if not hasattr(module, "renderAll") or not hasattr(module, "renderDepth"):
        return None
    return module.renderAll.__globals__


def _patch():
    if not _enabled:
        return False
    namespace = _namespace()
    if namespace is None:
        return False
    state = namespace.get(_KEY)
    if state and namespace["renderDepth"] is state["replacement"]:
        return True

    original = namespace["renderDepth"]
    # Leave future Labs implementations alone if they stop using the old ROP.
    if "opengl_depth" not in original.__code__.co_consts:
        # The exact path can also appear as '/opengl_depth'.
        if not any(isinstance(value, str) and "opengl_depth" in value
                   for value in original.__code__.co_consts):
            _log("Unsupported or already customized Labs Depth; left unchanged.")
            return False

    def modern_depth(node, single_pass=True):
        print("[Modern Depth] Labs Depth -> Flipbook ROP (Lighting Off)", flush=True)
        return _render_modern_depth(node, namespace, single_pass)

    namespace[_KEY] = {"original": original, "replacement": modern_depth}
    namespace["renderDepth"] = modern_depth
    _log("Enabled for {} on Houdini {}".format(_TYPE, hou.applicationVersionString()))
    return True


def _scene_event(event_type):
    if event_type in (hou.hipFileEventType.AfterLoad, hou.hipFileEventType.AfterClear):
        try:
            _patch()
        except Exception:
            _log(traceback.format_exc())


def _asset_event(event_type, **kwargs):
    try:
        _patch()
    except Exception:
        _log(traceback.format_exc())


def enable():
    global _enabled, _registered
    _enabled = True
    if not _registered:
        hou.hipFile.addEventCallback(_scene_event)
        hou.hda.addEventCallback(
            (hou.hdaEventType.LibraryInstalled, hou.hdaEventType.AssetCreated),
            _asset_event,
        )
        _registered = True
    return _patch()


def disable():
    """Disable this session. Package enable=false disables future startups."""
    global _enabled
    _enabled = False
    namespace = _namespace()
    if namespace is not None:
        state = namespace.pop(_KEY, None)
        if state and namespace["renderDepth"] is state["replacement"]:
            namespace["renderDepth"] = state["original"]
    _log("Disabled for the current session.")


def status():
    namespace = _namespace()
    state = namespace.get(_KEY) if namespace else None
    routed = bool(state and namespace["renderDepth"] is state["replacement"])
    return {"enabled": _enabled, "depth_uses_flipbook": routed,
            "houdini": hou.applicationVersionString(), "labs_type": _TYPE}


def show_status():
    info = status()
    message = ("Modern Depth: {}\n\n"
               "Labs Render Depth uses Flipbook ROP with Lighting Off.\n"
               "Applies to existing projects and newly created Labs nodes.\n"
               "No manual script is needed after restarting Houdini.\n\n"
               "Only Depth is changed; other render passes are unchanged.\n"
               "The original Labs menu may still say OpenGL ROP.").format(
                   "ACTIVE" if info["depth_uses_flipbook"] else "INACTIVE")
    if hou.isUIAvailable():
        hou.ui.displayMessage(message, title="Modern Depth")
    else:
        print(message)
