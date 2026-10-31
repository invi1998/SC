# Modern Depth：Houdini 22.0 自动深度修复

启动 Houdini 时自动将原版 `labs::flipbook_textures::1.0` 的 Render Depth 转到内置 Flipbook ROP，并关闭该深度节点的灯光、光追。继续使用原来的 Labs 节点和按钮；不需要每次运行脚本。启动工具本身不会渲染、模拟或保存工程。

用户工具安装位置：`C:/Users/shiheng/Documents/houdini22.0/codex_tools/modern_depth`。

自动加载配置：`C:/Users/shiheng/Documents/houdini22.0/packages/codex_modern_depth.json`。

重新打开 Houdini 后，已有工程和新建工程都生效。工具也会在加载 HIP、新建场景和安装 HDA 库后重新检查路由，不修改 SideFX Labs 安装文件。Render Depth 原菜单文字仍可能显示 OpenGL ROP，实际调用已替换。可通过 Modern Depth 工具架的 Depth Status 查看状态，或查看工具目录中的 `startup.log`。

深度逐帧输出原始 32 位 Pz，经 COP2 Mosaic 从左上角开始拼成图集，再交给原 Labs 合成和通道打包。帧数须等于格数，例如 4～67、步长 1 对应 8×8。其他渲染通道不变。

永久停用：将上述 JSON 中的 `"enable": true` 改为 `false`，然后重启 Houdini。卸载：删除这一份 JSON 配置和专属 `codex_tools/modern_depth` 文件夹即可。

当前适配 Houdini 22.0 / Python 3.13 / Labs Flipbook Textures 1.0。未来 Labs 改写深度实现后，工具会拒绝覆盖不认识的函数；升级 Houdini 大版本时需重新验证。

验证记录：安装后启动全新的 hython 进程，未手动运行修复命令即自动生效；通过原节点 `render_d` 按钮渲染 BurnSomke 缓存第 43～46 帧，得到 256×256 的 2×2 图集，Pz 有效像素 34445 个，深度范围约 14.849～26.563。新建多个原版 Labs 节点、File New、打开已有工程以及停用／重新启用均通过。完整 64 帧生产分辨率尚未重渲染；原 HIP 和正式贴图未被覆盖。
