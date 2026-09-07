# 排版引擎维护说明

默认规则从语义内容和蓝图生成正文；精度依靠共用字格、组件尺寸及光学参数，不靠逐题坐标。使用边界见[生成规则说明](RULE-LAYOUT.md)，配置定义见 [SCHEMA](SCHEMA.md)。

## 模块导航

| 文件（引擎文件位于 `engine/`） | 职责 |
| --- | --- |
| `build.py` | 读取 YAML、合并蓝图、选题编号、模式选择及构建归档 |
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
| `legacy_layout.py`、`reference_components.py` | 仅旧入口加载：蓝图兼容策略、正文及局部精确复用 |
| `scene.py` | 场景片段锚点变换，保留矢量图形状态 |
| `calibrated_renderer.py` | 各模式共用的 scene → LaTeX → XeLaTeX 输出 |

## 入口与不变量

无参数与 `--rules` 使用 `RuleLayout`，不加载 `legacy_layout`、`reference_components`，不读取旧正文绑定、逐字槽位、内容指纹或旧素材绑定。封面素材由独立模板声明，正文素材来自当前内容；只解析最终页面引用的素材。独立模板不得重新引入正文精确依赖。

已弃用的 `--precise` 在兼容时复用旧位置，失败后由 `CalibrationMismatch` 触发旧流排；`--recompose` 直接使用旧流排，两者均不是当前规则版。旧数据仍供迁移回归与诊断使用，不可仅因入口弃用就删除，也不可放宽兼容契约来强行复用。

`RuleLayout` 与 `LegacyLayout` 分别继承公共 `ComponentLayout`，不互相继承。公共层只负责起排、逐项组合与绘制；精确题组、标题、听力示范、排序例题和对页材料复用均在旧适配器中。`LegacyPolicy` 集中旧蓝图契约及参考插页判断；规则版不创建它，也不注入或强制关闭 `use_measured` 等内部开关。

- 测量与绘制共用计划；`ComponentLayout.choice_metrics()` 汇总题干、选项和列宽，不重复计算整套旧计划。
- 布局采用 bp、左上角原点、向下为正；scene 中的文字和图片采用 PDF 左下角坐标，仅在输出边界转换。
- `body_grid`、`CHOICE`、`CLOZE_BOX` 的尺寸同时服务占位和绘制；字距、基线、线宽等校准值不能随意取整。
- 跨页前保存 `x - body_left`，换页后使用新页的 `body_left`；旧片段的 `place_fragment()` 还必须保留矢量共享图形状态。
- 组合类只接管自己负责的块，其余交回 `super()`；新增角色先定义语义和尺寸计划，再增加绘制。

## 题组起排

公共流程为 `render_group()` 初始化 → `begin_group()` 定位 → `compose_group()` 组合标题与题目。局部扩展使用 `group_opening()`、`render_item()`、`reference_material()`，不复制整套循环。`new_page: true` 另起页；规则版的 `false` 从当前游标续排，旧适配器则拒绝在已有内容的页面上继续，避免替换旧页面。

`RuleLayout.heading_plan()` 与 `GroupFlow.first_item_keep()` 合并标题、正文偏移和首项的最小/优先保留高度。规划不绘制、不创建页面、不推进编号；临时材料状态须恢复，返回的选择题和听力计划供绘制复用。

当前页不足则整体换页；只有标题与优先整块超过一张新页时，才放宽首项可拆内容的整块保留。硬性最小单元仍放不下则报错，不反复换页。首项缓存与框拆分目标必须局部生效，不能误伤后续同内容组件。

`group_gap` 仅用于同页承接并容纳标题上伸；`start_on` 对续排检查当前页，由 `RuleLayout` 处理，`build.py` 不重复按下一页预对齐。跨科目、对页与听力面板约束优先。具体参数见[组卷蓝图](SCHEMA.md#组卷蓝图)。

## 回归检查

先保存改动前的同模式 PDF 到独立基准目录，再运行测试；共享引擎改动须分别构建 A、B、2014 的文字卷与听力卷，并覆盖默认规则、旧精确和旧流排三种模式。字体前提见 [FONTS](FONTS.md)。

```sh
python3 -m unittest discover -s tests
python3 tests/verify_examples.py --expected-dir tmp/layout-baseline/rules \
  --actual-dir output/rules paper-a-written paper-a-listening
python3 tests/verify_examples.py
```

基准使用 `N1-paper-a-written.pdf` 这样的文件名；可替换题册参数及两侧目录。工具默认比较 `examples/` 与 `output/rules/` 中 A 的两份题册，逐页检查 2 倍栅格像素，而非 PDF 二进制。旧模式须显式指定同模式的基准与输出目录；旧版无参数基准归入 `precise`，各模式之间不要求相同断行、分页或像素。

同页逻辑另测页底、标题注音、过长首项、框和表格、跨科目、对页及听力；新增场景通过不能代替标准蓝图回归。默认构建须在旧模块不可导入、旧正文数据不可读取时成功；误传旧复用开关也不得改变输出。

发生像素变化时渲染相关页面，与[官方原稿](https://www.jlpt.jp/samples/sampleindex.html)及已确认成品核对注音、下划线、框线、小注和跨页元素。同模式回归不等于与官方稿一致；外观诊断命令见[生成规则说明](RULE-LAYOUT.md#检查外观与扩展性)。

只有确认属于预期变化才更新 `examples/`；生成了新的 PDF 二进制本身不是覆盖展示样例的理由。不要把临时测试数量或某轮差分结果写成持续有效的保证。
