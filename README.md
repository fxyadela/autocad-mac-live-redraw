# AutoCAD Mac 原生重绘 Skill

一个供豆包工作等具备本地电脑操作能力的 AI 代理使用的实验版 Skill：先把二维图纸整理成有证据、坐标、图层和图元的 JSON 清单，再生成 AutoCAD for Mac 可加载的 AutoLISP，先定位空白画布，再按顺序逐个显示真正可编辑的 CAD 对象；已有完整 DXF 时也可选择在 AutoCAD 中打开并另存为 DWG。

> **状态（2026-09-16）：实验版。** “预先定位画布、逐个原生图元刷新、每个图元短暂停顿”的编译逻辑和离线测试已通过；合成小样已在 AutoCAD 2027 for Mac 实机完成 `CADLIVE`，确认生成 13 个原生模型空间对象。命令自动加载 bundle 已加入单键 `K`、`CADLIVE` 和 `CADFAST` 注册并通过离线部署测试；`K` 用于避免桌面代理只送入 `CADLIVE` 首字母而误启 `CIRCLE`。新清单仍需在 AutoCAD 中实机验证；复杂户型的逐个显示、DWG 保存与重开编辑也需分别验收。本项目不保证“上传图片就能自动准确出图”，请勿将小样测试视为正式图纸交付证明。

## 适用范围与条件

- macOS、本机安装并能正常进入画布的 AutoCAD for Mac，以及 Python 3.10 或更新版本（编译器仅用标准库）。使用豆包时还需要豆包工作的“本地电脑／操作电脑”能力；Skill 不会自行取得桌面权限或软件许可。
- 只处理模型空间的二维图元。它不是图片识别模型；文字转录、比例校准、尺寸核对和结构化清单仍需要 AI 与人复核。无可信物理尺度时必须写 `unitless`。
- 原生逐图元路径支持墙线、多段线、矩形、圆、弧、单/多行文字、两种原生尺寸等，详见 [输入规范](references/spec.md)。表格、填充、椭圆、径向尺寸、特殊字体/线型等当前不支持，编译会拒绝，不会假装画完。
- 此仓库是独立 Skill，不包括 AutoCAD、豆包或 Autodesk 的许可证，也不是这些产品的官方插件。

## 安装到豆包工作（Mac）

1. 在本仓库点 **Code → Download ZIP** 并解压；也可以运行 `git clone https://github.com/fxyadela/autocad-mac-live-redraw.git`。找到解压后**包含 `SKILL.md`、`scripts/` 和 `references/` 的整个仓库文件夹**，不要只下载或选择 `SKILL.md` 一个文件。
2. 打开豆包工作桌面端，进入“连接器 · 技能 · 伙伴” → “技能”，打开页面上的菜单，选择“上传技能” → “选择文件夹”，选上一步的整个文件夹。此流程基于 2026-09-15 的 Mac 客户端界面；若 UI 改版，按当前“上传技能”入口并确认导入要求。上传会把选中的 Skill 文件交给豆包服务；本仓库不含个人图纸。
3. 确认技能列表出现 `autocad-mac-live-redraw`。在新对话启用“本地电脑”，用输入框中的 `/ 使用技能` 查找并调用它。**列表出现只证明导入，不证明 AutoCAD 已能操作。**

其他支持文件夹式 Skill 的代理也可导入仓库根目录，但其桌面操作权限、技能发现方式和原生绘图结果都应分别核验；不能把在豆包导入成功外推为所有代理可用。

## 先做一个安全的小样

仓库提供 [测试清单](references/sample-spec.json)，它是合成图，不是任何人的正式图纸。在仓库根目录运行：

```bash
python3 scripts/compile_mac_redraw.py \
  --spec "$(pwd)/references/sample-spec.json" \
  --out "$(pwd)/sample-redraw.lsp" \
  --delay-ms 35
```

编译成功只产生 `.lsp`，不会打开 AutoCAD、保存 DWG 或修改既有图纸。再运行编译器输出的 `deploy_autocad_bundle.py` 命令，把当前 LSP 部署到用户级 `ApplicationAddins` bundle。部署结果为 `BUNDLE_UPDATED` 时不重启，只需新建空白图；首次安装或命令清单升级时，如果 AutoCAD 已打开，用 `_APPAUTOLOADER` → `_Reload` 刷新一次插件，然后新建空白图。画布命令栏必须先处于空闲状态；若显示 `CIRCLE`/`SAVEAS` 等参数提示，按一次 Escape。随后只按单键 `K` 和 Return 启动逐图元绘制，不用桌面代理输入完整 `CADLIVE`。不要输入长 AutoLISP 表达式，不要退出重启，不要打开 `APPLOAD`、帮助页、F1、浏览器或“已加载的应用程序”列表。若 `K` 未识别、出现 `CADREDRAW FAILED`、画布未完成或对象数不符，立即停止且不保存部分图纸。成功后另存为**新的 DWG**，关闭重开，并实际选中/修改一个图元检验可编辑性。

如果交给豆包完成小样，可以这样说：

> 请使用 autocad-mac-live-redraw，在本机 AutoCAD 的新空白图里先运行仓库提供的测试清单，逐步画出对象并另存为新的 DWG。关闭重开后选中修改一条墙线，告诉我哪些步骤亲眼完成；如果 AutoCAD 不可操作，就停下来报告，不要只给预览图。

正式图纸应先按 [输入规范](references/spec.md) 建立清单并核对原图，再走原生绘制；若图纸有编译器不支持但已有高质量 DXF 的完整内容，可选择在 AutoCAD 中打开 DXF、另存 DWG、重开编辑的保真路径。这条路径**不是**从空白逐笔画的演示。完整操作约束在 [SKILL.md](SKILL.md)。

## 本地离线测试

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

当前仓库提供可在本机运行的离线测试；尚未配置 GitHub Actions，测试不运行 AutoCAD。欢迎通过 Issues 提交 AutoCAD 原生测试日志、可分享的最小复现清单及改进建议；请不要上传含住址、个人信息或私密图纸的真实文件。

## 许可

本项目的代码与文档采用 [MIT License](LICENSE)。这允许他人使用、修改与再分发本 Skill，但不授权 AutoCAD 或豆包产品本身。
