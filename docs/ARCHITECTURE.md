# 排版引擎维护说明

默认规则从语义内容和蓝图生成正文；精度依靠共用字格、组件尺寸及光学参数，不靠逐题坐标。使用边界见[生成规则说明](RULE-LAYOUT.md)，配置定义见 [SCHEMA](SCHEMA.md)。

## 模块导航

| 文件（引擎文件位于 `engine/`） | 职责 |
| --- | --- |
| `build.py` | 读取 YAML、合并蓝图、选题编号及构建归档 |
| `rule_layout.py`、`group_flow.py` | 默认入口、题组起排、标题与首项保留计划 |
| `written_rules.py`、`listening_rules.py` | 标题测量与绘制、题型说明、听力和图注 |
| `choice_rules.py`、`reading_rules.py` | 题干选项、段落、字距、小注、通知与完形框 |
| `vertical_rules.py`、`reference_rules.py` | 竖排引用、结构化参考文档 |
| `component_layout.py`、`material_primitives.py` | 共用组合、分页、编号、图片、表格与方框 |
| `inline.py`、`geometry.py`、`rule_typography.py` | 文字单元、版心网格、字体字格与行内绘制 |
| `cover_templates.py`、`ordering_templates.py` | 独立封面、固定排序说明与示范 |
| `component_fonts.py`、`font_overrides.py` | 字体选择、同字体补字与配置校验 |
| `metadata_bindings.py`、`metadata_components.py`、`page_furniture.py` | 元数据、封面文字适配、页眉页码与分区标记 |
| `rule_validation.py` | 角色、嵌套和有效尺寸检查 |
| `calibrated_renderer.py` | 生成的 scene → LaTeX → XeLaTeX 输出 |

## 入口与不变量

构建使用 `RuleLayout`，由共享规则从当前内容计算正文。封面和排序示范使用独立模板；只解析最终页面引用的素材。

`RuleLayout` 继承 `ComponentLayout` 的组合与绘制能力，并通过题型规则处理断行、字距和分页。旧精确入口、兼容适配器及正文绑定数据已移除；历史实现可从 Git 记录恢复。

- 测量与绘制共用计划；`ComponentLayout.choice_metrics()` 汇总题干、选项和列宽，不重复计算整套旧计划。
- 布局采用 bp、左上角原点、向下为正；scene 中的文字和图片采用 PDF 左下角坐标，仅在输出边界转换。
- `body_grid`、`CHOICE`、`CLOZE_BOX` 的尺寸同时服务占位和绘制；字距、基线、线宽等校准值不能随意取整。
- 跨页前保存 `x - body_left`，换页后使用新页的 `body_left`。
- 组合类只接管自己负责的块，其余交回 `super()`；新增角色先定义语义和尺寸计划，再增加绘制。

## 题组起排

公共流程为 `render_group()` 初始化 → `begin_group()` 定位 → `compose_group()` 组合标题与题目。局部扩展使用 `group_opening()`、`render_item()`、`reference_material()`，不复制整套循环。`new_page: true` 另起页；`false` 从当前游标续排。

`RuleLayout.heading_plan()` 与 `GroupFlow.first_item_keep()` 合并标题、正文偏移和首项的最小/优先保留高度。规划不绘制、不创建页面、不推进编号；临时材料状态须恢复，返回的选择题和听力计划供绘制复用。

当前页不足则整体换页；只有标题与优先整块超过一张新页时，才放宽首项可拆内容的整块保留。硬性最小单元仍放不下则报错，不反复换页。首项缓存与框拆分目标必须局部生效，不能误伤后续同内容组件。

`group_gap` 仅用于同页承接并容纳标题上伸；`start_on` 对续排检查当前页，由 `RuleLayout` 处理，`build.py` 不重复按下一页预对齐。跨科目、对页与听力面板约束优先。具体参数见[组卷蓝图](SCHEMA.md#组卷蓝图)。

## 回归检查

先保存改动前的 PDF 到独立基准目录，再运行测试；共享引擎改动须构建 A、B、2014 的文字卷与听力卷共六份题册。字体前提见 [FONTS](FONTS.md)。

```sh
python3 -m unittest discover -s tests
python3 tests/verify_examples.py --expected-dir tmp/layout-baseline/rules \
  --actual-dir output/rules paper-a-written paper-a-listening
python3 tests/verify_examples.py
```

基准使用 `N1-paper-a-written.pdf` 这样的文件名；可替换题册参数及两侧目录。工具默认比较 `examples/` 与 `output/rules/` 中 A 的两份题册，逐页检查 2 倍栅格像素，而非 PDF 二进制。只清理实现和资源时，六份题册应与清理前逐页像素一致。

同页逻辑另测页底、标题注音、过长首项、框和表格、跨科目、对页及听力；新增场景通过不能代替标准蓝图回归。A卷断行基准仅供诊断，不能被运行引擎读取或用于决定分页。

发生像素变化时渲染相关页面，与[官方原稿](https://www.jlpt.jp/samples/sampleindex.html)及已确认成品核对注音、下划线、框线、小注和跨页元素。同模式回归不等于与官方稿一致；外观诊断命令见[生成规则说明](RULE-LAYOUT.md#检查外观与扩展性)。

只有确认属于预期变化才更新 `examples/`；生成了新的 PDF 二进制本身不是覆盖展示样例的理由。不要把临时测试数量或某轮差分结果写成持续有效的保证。
