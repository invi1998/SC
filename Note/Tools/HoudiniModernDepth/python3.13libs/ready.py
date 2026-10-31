"""Load after assets are available, in GUI and batch Houdini sessions."""
try:
    import codex_modern_depth
    codex_modern_depth.enable()
except Exception as exc:
    print("[Modern Depth] Startup failed: {}".format(exc))
