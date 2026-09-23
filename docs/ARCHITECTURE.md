# 开发与维护

日常换题优先编辑内容/蓝图，不必改引擎。首次运行见 [README](../README.md)，字段和命令见 [SCHEMA](SCHEMA.md)，成品外观要求见 [排版规则](RULE-LAYOUT.md)与[验收清单](../.agents/skills/jlpt-typeset/references/quality-checks.md)。

## 仓库地图

| 路径 | 用途 |
| --- | --- |
| `build.py` | 读配置、选题编号、排版、编译及归档的统一入口 |
| `content/<paper>/` | V/G/R/L 题文；`content/common/metadata.yaml` 提供默认封面和页眉等元数据 |
| `blueprints/` | 组卷顺序与布局意图；components按题型提供默认值 |
| `fonts.yaml` | 未填路径的公开字体配置示例；个人配置放 `private/` |
| `resources/assets/` | 题图、背纹、隔页花纹等引用素材 |
| `profiles/n1-original/` | 字体目录与子集、固定封面/排序模板、TeX绘图样式 |
| `engine/` | 共用文字测量、组件布局、分页及场景渲染 |
| `examples/` | 六份展示与回归PDF；不随构建自动更新 |
| `tests/` | 单元/边界测试和PDF诊断工具，测试数据不参与生产分页 |
| `docs/`、`.agents/skills/jlpt-typeset/` | 人与AI共用的配置/维护说明，以及技能流程/验收清单 |
| `output/`、`tmp/` | 默认忽略的生成工程及临时对比；不是发布源文件 |

构建链为 YAML与蓝图 → `RuleLayout` / `ComponentLayout` → scene → TeX → PDF。封面与排序示范使用独立模板；可变正文按内容测量，只解析最终页面引用的素材。

## 模块地图与测试入口

所有引擎文件位于 `engine/`，测试位于 `tests/`；按实际变动选择有判别力的边界测试，不需要为了文档改动新增“检查文案存在”的测试。

| 模块 | 负责什么 | 相关现有测试 |
| --- | --- | --- |
| `build.py`（根目录） | CLI、schema、选题重编号、元数据选择、输入快照与报告 | `test_build_validation.py`、`test_build_refactor.py` |
| `rule_layout.py`、`group_flow.py` | 题组入口、同页接排、标题和首项保留 | `test_group_flow.py`、`test_same_page_groups.py`、`test_same_page_build.py` |
| `reading_rules.py` | 阅读/完形、notice/contact、自然段、框/注释、题目接排 | `test_reading_rules.py`、`test_reading_linebreaks.py`、`test_material_flow.py` |
| `spread_alignment.py` | 完整材料单元试排、奇偶起页与花纹隔页审计 | `test_spread_alignment.py` |
| `reference_rules.py`、`reference_document.py` | 信息检索材料、guide/reference及计划测量 | `test_reference_rules.py`、`test_reference_document.py` |
| `vertical_rules.py` | 竖排正文、出处、旁注、跨列和框 | `test_vertical_rules.py` |
| `choice_rules.py`、`written_rules.py` | 题干/选项/排序、题型标题和列宽 | `test_choice_rules.py`、`test_written_rules.py`、`test_ordering_example_layout.py` |
| `listening_rules.py` | 听力标题、说明、标签/注音及memo | `test_listening_rules.py`、`test_listening_table_spacing.py`、`test_same_page_listening.py` |
| `component_layout.py`、`material_primitives.py` | 组合布局、图表、方框、共用分页与保留；听力面板、嵌入选项、full_page_items调度在component_layout | `test_component_layout.py`、`test_material_primitives.py` |
| `inline.py`、`rule_typography.py`、`geometry.py` | ruby/小注/下划线文字单元、字距、字号、字形坐标 | `test_core.py`、`test_rule_typography.py`、`test_geometry.py`、`test_editorial_labels.py` |
| `component_fonts.py`、`font_overrides.py`、`font_subset.py` | 字体解析、同款补字、配置校验及子集 | `test_resolver_policy.py`、`test_renderer_helpers.py` |
| `cover_templates.py`、`ordering_templates.py` | 固定模板与当前文本绑定；排序模板不兼容时回退普通规则，封面超出模板约束时报错 | `test_cover_templates.py`、`test_ordering_templates.py` |
| `metadata_bindings.py`、`metadata_components.py`、`page_furniture.py` | 封面字段适配、页眉页码、侧栏 | `test_metadata_bindings.py`、`test_metadata_components.py` |
| `rule_validation.py`、`semantic_bindings.py` | 角色/嵌套/尺寸边界、语义记录 | `test_rule_validation.py`、`test_build_validation.py` |
| `calibrated_renderer.py`、`profiles/n1-original/n1-exact.sty` | scene→TeX→PDF、坐标变换及输出数值格式 | `test_renderer_helpers.py`、`test_scene_numbers.py`、`test_example_verification.py` |

## 实现约定

1. 先定义内容语义、适用块类型及可拆分边界，再写共用计划。测量、断行、分页、绘制必须使用同一计划；不能测量一套、绘制时另算一套，或用不一致的文字正规化。
2. 预览不得推进正式题号、页码、游标或语义账本。覆盖单页、双页、三页、右页已有内容、同页题组等情形；A/B 对比阅读是同一个单元。没有隔页素材时说明限制，不能让审计报告假装通过。
3. 内部布局以 bp、左上角原点和向下为正；scene文字/图片采用PDF左下角坐标，在边界转换。跨页先保存 `x - old_body_left`，后加新页版心，不能从旧绝对x直接放到新页。
4. `body_grid`、`CHOICE`、`CLOZE_BOX` 的占位与实际绘制一致。光学字距、线宽、ruby/小注偏移有作用，不因小数长就随意取整；普通正文禁止靠压行距修长文。
5. 数值精简只在写出 `scene.json` 时保持既有12位有效数字渲染参数；计算使用原精度。保护负零、大指数、布尔值、整数ID和字符串中的URL/向量命令。`0.999995`、`12.00001bp`、Bezier比例及容差可能改变渲染，不能一律四舍五入。
6. 新角色要在验证层定义支持的块类型和嵌套；不可容纳的内容显式报错，不能静默裁切、删条件、掉选项或循环产生空页。
7. 沿现有入口扩展 `group_opening()`、`render_item()`、`reference_material()` 等，不复制整个组卷循环；组合类只处理职责内块，其余交回公共实现。
8. 新测试使用合成内容覆盖真实行为边界；不把私人题文、未公开题库路径或用户本机字体位置写进公开测试。修改共享逻辑时按下方回归流程重建六份公开样例并完成视觉验收。

## 题组与材料流

`render_group()` 初始化 → `begin_group()` 定位 → `compose_group()` 组合标题与内容。局部扩展使用 `group_opening()`、`render_item()`、`reference_material()`；不要复制整套组卷循环。

`heading_plan()` 与 `GroupFlow.first_item_keep()` 规划标题和首项的最小/优先保留高度，不能绘制或推进正式状态。当前页不足时整体换页；只有整块超过新页余量时才放宽可拆首项，硬性最小单元仍超限则报错。临时状态及首项缓存必须局部生效，不能影响后续篇章。

多页材料对齐由 `spread_alignment.py` 试排完整单元；普通题组 `start_on` 与 `new_page: false` 的当前页逻辑由 `RuleLayout` 处理，不能再在build入口重复预对齐。`facing_pages` 的信息检索维持专用左题右图布局。

## 回归检查

按变化选择检查范围：题文只改一册时构建该册并复核受影响页及后续分页；共享引擎、公共模板或字体路由改动须运行全套测试并构建六份样例。文档改动检查链接/命令；仅源码说明改动可比较AST，确认执行逻辑不变，不必重编PDF。

先将改动前PDF保存到独立目录。以下命令使用已经配置好的 `private/fonts.yaml`，将候选产物写到 `output/review`：

```sh
python3 -m unittest discover -s tests
python3 build.py --paper paper-a --booklet written --fonts private/fonts.yaml --output-dir output/review
python3 build.py --paper paper-a --booklet listening --fonts private/fonts.yaml --output-dir output/review
python3 build.py --paper paper-b --booklet written --fonts private/fonts.yaml --output-dir output/review
python3 build.py --paper paper-b --booklet listening --fonts private/fonts.yaml --output-dir output/review
python3 build.py --paper paper-2014-12 --booklet written --blueprint blueprints/2014-12-written.yaml --fonts private/fonts.yaml --output-dir output/review
python3 build.py --paper paper-2014-12 --booklet listening --fonts private/fonts.yaml --output-dir output/review
python3 tests/verify_examples.py --actual-dir output/review --expected-dir examples \
  paper-a-written paper-a-listening paper-b-written paper-b-listening \
  paper-2014-12-written paper-2014-12-listening
```

`verify_examples.py` 默认只比较 A 两册，六册必须显式列出。它逐页比较2倍栅格像素，不比较PDF字节；`--expected-dir` 可换为保存的旧基准目录，文件名须同样为 `N1-paper-a-written.pdf` 等。

纯实现清理/数值精简应像素不变。刻意修改版式时，逐项解释并实际查看所有变化页及相邻页，分页变化继续检查后续单元；确认后才更新 `examples/`，不能通过覆盖失败基准让回归“通过”。像素回归、原稿对照、新内容边界测试分别证明不同事情，不互相替代。

新增布局逻辑至少覆盖其相关的长文/长注音/显式换行/窄版心/表格增行/左右换页/可拆边界；不可容纳要报错，不能静默删字或裁切。针对性测试可用 `python3 -m unittest discover -s tests -p 'test_spread_alignment.py'`，不代替共享改动的全套回归。

### 辅助诊断

```sh
python3 tests/compare_rule_layout.py examples/N1-paper-a-written.pdf \
  output/review/N1-paper-a-written.pdf --output tmp/layout-diff.json
python3 tests/check_rule_a_rows.py --fonts private/fonts.yaml --output tmp/a-rows.json
```

- `compare_rule_layout.py` 默认跳过前两页汇总，并裁去页缘/页脚的比较区域；退出0仅表示页数相同，须读报告。差异与原稿墨迹的比值不是相似度，可超过100%。页面增删后按题号/材料对齐比较，不能机械比较同一页序。
- `check_rule_a_rows.py` 使用当前A题文与固定断行fixture作诊断；不自动读取根目录fonts.yaml，需显式指定与构建相同的配置。它不检查其它题库，不能决定生产断行，也不代替最终看图。
- 实际渲染与整页/双页检查方法统一见[验收清单](../.agents/skills/jlpt-typeset/references/quality-checks.md#如何做视觉检查)。

## 维护文档与准备发布

每类事实只维护一个主要入口：README负责起步；CONTENT-GUIDE负责编辑流程；SCHEMA负责字段/CLI/产物；FONTS负责字体；RULE-LAYOUT负责版式；本文件负责模块与回归；技能引用这些文档，保留操作流程和验收经验。

发布前检查实际变更与交付清单：

- 通用行为/字段改动同步对应文档，真实失败补最小合成回归用例；不写只检查文案是否出现的测试。
- 已获准更新的六份公开示例通过验收后再替换，不把临时PNG、TeX工程、原始压缩包或旧版一起分发。
- 公共题库仅A/B及既有2014样例；新题库、完整字体、个人路径、日志和凭据不进入提交。保留`.gitignore`的允许列表，不强制添加私有资料。
- 核 `git diff --check`、`git status --short` 与实际暂存清单；公共字体子集/素材即使本次样例没有画出某字也可能被新内容复用，不能按一次构建的使用记录删掉。
