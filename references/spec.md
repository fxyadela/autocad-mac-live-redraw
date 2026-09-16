# Mac 本机 AutoCAD 重绘清单

JSON 根节点：`metadata`、`layers`、`entities`。此格式兼容 `autocad-image-redraw` 的 image-redraw spec v2；`source`、`views`、`calibration`、`constraints` 等证据字段原样保存，Mac 编译器只绘制明确列出的 `entities`，不负责 OCR 或比例推断。

```json
{
  "schema_version": "2.0",
  "metadata": {"title": "测试图", "units": "mm", "source_image": "/绝对路径/原图.png"},
  "source": {"path": "/绝对路径/原图.png"},
  "calibration": [{"method": "dimension-anchor", "value": 3000, "units": "mm"}],
  "layers": [
    {"name": "WALL", "color": 7, "linetype": "Continuous"},
    {"name": "DOOR", "color": 2, "linetype": "Continuous"},
    {"name": "DIM", "color": 3, "linetype": "Continuous"}
  ],
  "entities": [
    {"type": "line", "layer": "WALL", "start": [0, 0], "end": [3000, 0], "evidence_level": "known"},
    {"type": "arc", "layer": "DOOR", "center": [0, 0], "radius": 900, "start_angle": 0, "end_angle": 90},
    {"type": "aligned_dimension", "layer": "DIM", "p1": [0, 0], "p2": [3000, 0], "dimline": [1500, -200]}
  ]
}
```

`units`: `unitless`, `mm`, `cm`, `m`, `in`, `ft`；不能确定就写 `unitless`。点均是 `[x,y]` 或 `[x,y,z]`，绘制只支持模型空间平面（`z=0`）。角度是度。图元按 `entities` 顺序逐一展示，在 JSON 中先排墙/结构，再门、窗、尺寸、标签。文本 `height` 为 CAD 单位，圆/弧半径必须大于零；`text` 单行，`mtext` 可多行且需要 `width`。

支持的形状：`line(start,end)`；`polyline(points,closed?)`；`rectangle(p1,p2)` 或 `rectangle(x,y,width,height)`；`circle(center,radius)`；`arc(center,radius,start_angle,end_angle)`。文字：`text(text,point,height?,rotation?)`、`mtext(text,point,width,height?,rotation?)`。`leader(points,text,text_point?,text_height?)` 实现为可编辑 LINE+TEXT，不是原生 LEADER；`center_mark(center,size?)` 是两条 LINE。原生可编辑尺寸：`linear_dimension(p1,p2,dimline,angle?,text?)`、`aligned_dimension(p1,p2,dimline,text?)`。尺寸 `text` 如原图明显与计算值不同，必须标明是文字覆盖而非真实测量。

图层名需符合 AutoCAD 字符规则，层 `color` 为 1–255，`linetype` 当前只接受 `Continuous`。图元可单独设 `color` 1–255。未声明的图层可自动建立默认白色。`text_style`/特殊字体、虚线和 `table`、`radial_dimension`、`hatch`、`ellipse` 等非支持图元 **不会静默省略**，必须换完整 DXF 保真路线、另作开发或说明未交付。OCR/标注证据应继续保存在 `source_refs`、`confidence`、`notes` 等字段。

输出的 `.lsp` 需要在本机 AutoCAD 新建空白图经 APPLOAD 加载；`CADLIVE` 会预先定位视口并逐个显示原生图元，`CADFAST` 为无停顿核验。导出的 DWG 须另存、重开、实际选中图元和对照原图，离线编译成功不能替代这些检查。
