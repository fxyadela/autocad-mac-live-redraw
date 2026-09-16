---
name: autocad-mac-live-redraw
description: 在 macOS 的本机 AutoCAD 中，把已校准的二维重绘清单按图元逐一画成可编辑 CAD 图形，或将现有 DXF 导入另存为 DWG。适用于豆包工作等具备本地电脑操作能力的代理；不适用于 Windows COM 自动化。
---

# AutoCAD for Mac 本机重绘

这是自包含的 **Mac 原生适配**，无需安装其他 CAD 技能；不调用 `win32com`、`pywin32`、`taskkill`。豆包或其他代理执行本技能，须另有本地电脑操作能力且当前 Mac 的 AutoCAD 可交互；技能文字和离线文件本身不会自动获得桌面权限。目前脚本通过离线测试，合成小样已在 AutoCAD 2027 for Mac 实机完成逐图元绘制；复杂正式图纸和 DWG 交付仍须逐次验证。

## 首先确定是哪一种交付

- 用户要看到从空白画布逐步画出可编辑对象：按 [输入规范](references/spec.md) 从原图建立证据约束、尺寸校准、坐标/图层/图元的 JSON 清单，再用 `scripts/compile_mac_redraw.py` 生成本机 AutoLISP，进入“原生逐步绘制”流程。
- 用户已有完整 DXF，优先保真：用本机 AutoCAD 的图形界面打开 DXF，再 **另存为新的 DWG**，关闭后重开检验。DXF 本身也包含可编辑 CAD 图元，但打开现成 DXF 不是从空白逐笔画的演示。
- 不要把 STEP/机械建模或 QCAD 的 JS `-exec` 当成 AutoCAD for Mac 的原生操控方式。

## 原图到清单（两条路线共同前提）

1. 读取原图和可辨尺寸，记录来源、比例依据、单位、模糊项。无可靠尺度时用 `unitless`；不要把像素直接宣称为毫米。先转录文本/尺寸，再重建墙、门、窗、轴网、房间文字和标注的 CAD 坐标。图纸所含的表格、填充等复杂内容也须记录，不得为了让程序成功而漏掉。
2. 优先复用用户现有的高质量 DXF/结构化 JSON，检查图元数量、类型、层和尺寸，以及图片对照；不能凭“DXF 有实体”推断和原图完全一致。
3. 每个清单图元均应注明其证据（已知、校准缩放、推断、不可辨）。具体可执行字段和局限见本技能的 [输入规范](references/spec.md)；不要依赖用户另装其他技能才能运行。

## 生成原生可见绘制脚本

从技能目录运行（不要替换现有文件）：

```bash
python3 scripts/compile_mac_redraw.py --spec /绝对路径/重绘清单.json --out /绝对路径/新图绘制.lsp --delay-ms 35
```

编译阶段先严格核验字段、非有限数字、图层、单位、所有类型；仅支持 `line`, `polyline`, `rectangle`, `circle`, `arc`, `text`, `mtext`, `leader`（线段加文字，并非原生 LEADER）, `linear_dimension`, `aligned_dimension`, `center_mark`。`table` 和 `radial_dimension` 等当前不支持，编译会失败；需要这些内容时选择完整 DXF 导入路线或进一步实现适配，不能只画几根线就说图纸完成。`text_style`/非连续线型/复杂尺寸样式未在此编译器实现，遇到明确请求亦会失败。主路径会在开始前定位整张图的视口，再按清单顺序每创建一个原生图元立即显示；`--delay-ms` 控制每个图元后的短暂停顿，推荐 25–40 毫秒以兼顾流畅度和可见性。默认无自动覆盖、清空或保存。

编译后从技能目录在后台部署当前脚本：

```bash
python3 scripts/deploy_autocad_bundle.py --lsp /绝对路径/新图绘制.lsp
```

它把当前 LSP 放入当前用户的 AutoCAD `ApplicationAddins/AutoCADMacLiveRedraw.bundle`，并在 bundle 清单中注册数字单键命令 `1`、完整命令 `CADLIVE` 和无停顿核验命令 `CADFAST`，由 AutoCAD 在调用命令时加载。部署输出会明确标记 `BUNDLE_INSTALLED`、`BUNDLE_UPGRADED` 或 `BUNDLE_UPDATED`；此目录只用于本技能自己的 bundle，不修改 `SECURELOAD`、`TRUSTEDPATHS` 或 Autodesk 安装目录。

## 豆包在 Mac AutoCAD 的实际操作

1. 在切换到 AutoCAD 前，先在后台完成识图、清单校验、LSP 编译和 bundle 部署；不要让用户观看代理在文件窗口中反复找文件。确认豆包的本地电脑/操作电脑功能实际可用且 AutoCAD 主界面/许可状态正常。若原生应用打不开、弹许可窗口、指令无响应，先报告这个阻断；进程存在 ≠ 绘图画布可用。不得用静态预览伪装应用操作。
2. 严格按部署输出处理。`BUNDLE_UPDATED`：不退出、不重启 AutoCAD，直接新建空白图。`BUNDLE_INSTALLED` 或 `BUNDLE_UPGRADED`：AutoCAD for Mac 没有 `_APPAUTOLOADER` 命令；若 AutoCAD 已打开，在正式绘图任务开始前关闭并正常启动一次，让新命令清单被发现；若尚未打开，正常启动即可。这是安装/升级后的单次准备，不是失败恢复；任务中不得再反复重启。不要打开 `APPLOAD`，也不要查看“已加载的应用程序”列表。
3. 整个绘图阶段必须留在 AutoCAD；不得按 F1、点击帮助/问号、打开或切换浏览器，也不得在没有看见弹窗时猜测“安全确认正在等待”并全屏搜索。若意外出现浏览器或 Autodesk 帮助页，立即停止并报告误触，不得返回 AutoCAD 继续重试。
4. 先看命令栏是否为空闲的“键入命令/Command:”。若仍显示 `CIRCLE`、`SAVEAS` 或其他参数提示，只按一次 Escape；未回到空闲状态就停止报告。空闲后单击输入区一次，用 `type_text` 只输入单个字符 `1`，再按 Return 一次。`1` 是专为桌面操作长文本被截断而注册的单键绘制命令；不得通过 `type_text`/`set_value` 输入 `CADLIVE`，否则只送入首字母 `C` 时会误启动 `CIRCLE`。不要输入以 `(` 开头的 AutoLISP 表达式。若 `1` 一次执行后仍未出现 `CADREDRAW loaded.` 和首个图元，停止并报告命令栏原文；不得重启、打开 APPLOAD、搜索文件、检查安全弹窗或再次提交命令。
5. `1` 应让图元在已定位的画布上一个接一个出现；`CADLIVE` 只作为人工键盘的完整名称备用，只有做无停顿核验时才使用 `CADFAST`。不要通过打开预先生成的 DWG/DXF 冒充逐一绘制。脚本拒绝在已有模型空间对象的图中重复执行。中文字符依赖当前 AutoCAD 文字引擎及字体，视觉复查必须包含中文、尺寸箭头和图层。
6. 看见命令栏的完成信息后，检查画布对象数和进度；若有 `CADREDRAW FAILED` 或中途停止，不保存部分图纸，不要声称成功。核对原图的重要尺寸、墙线门窗、文字/表格/填充，不合格则返修清单再重画。若旧 DXF 路线，在 UI 打开现有 DXF 并看其全部内容，而不是打开自动生成的演示预览。
7. 用 AutoCAD 的“另存为”选择 **DWG**，保存到新的绝对路径。关闭并重开这个 DWG；在本机点击/修改至少一个墙线、门窗、文字或标注对象，检查层与尺寸，必要时再保存。保留原图、清单、LSP、DXF 和 DWG 的独立路径；不覆盖源文件。
8. 汇报分开列：清单校准与原图准确度、LSP/DXF 离线校验、AutoCAD 实际加载和逐步绘制、DWG 保存、重开编辑/视觉对照。每级缺证据就标“未验证”，不能靠日志或视频推断交付完成。

## 使用边界

AutoCAD for Mac 官方支持 AutoLISP（`entmake`、`command-s`），不支持 Windows ActiveX/COM 工作流。编译器是当前明确可测试的 Mac 桥接部分，不是对任意扫描图的自动识图工具；完整的图纸重绘仍需要可信的测绘/文字核对。不能加载 LSP 的安全弹窗和应用不可交互是执行前提的阻断，不能绕过系统权限。
