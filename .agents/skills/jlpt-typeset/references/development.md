# DIY 与引擎开发

## 先选择修改层

| 目的 | 修改入口 | 不应依赖 |
| --- | --- | --- |
| 换题、校字、ruby、小注、图表内容 | `content/<paper>/*.yaml`，见 [SCHEMA](../../../../docs/SCHEMA.md) | 输出TeX、旧PDF的每行坐标 |
| 选题、顺序、列数、题组分页意图 | `blueprints/*.yaml` 与 `components.yaml` | 把 `source_pages` 当输出分页 |
| 年份、A/B、考试说明、隔页素材 | 整份 `metadata.yaml` | 按文件名猜圈标或隐式部分合并 |
| 完整字体补字或封面字体 | 私有 `--fonts` 配置，见 [FONTS](../../../../docs/FONTS.md) | 改系统字体、不同字族混补 |
| 改正文规则或新增可复用组件 | `engine/` 的语义规则＋共享测量/绘制计划 | 按年份/题号/正文字符串识别专属坐标 |
| 改固定封面/排序示范 | `profiles/n1-original/` 对应template及专属引擎 | 把它们推广为正文逐字坐标模板 |

一般出卷无需改 Python；已有公开样例和单元测试可帮助理解字段，但不能把一个例卷的页数或坐标写成所有卷的规则。

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

更多调用关系见 [ARCHITECTURE](../../../../docs/ARCHITECTURE.md)。

## 实现约定

1. 先定义内容语义、适用块类型及可拆分边界，再写共用计划。测量、断行、分页、绘制必须使用同一计划；不能测量一套、绘制时另算一套，或用不一致的文字正规化。
2. 预览不得推进正式题号、页码、游标或语义账本。覆盖单页、双页、三页、右页已有内容、同页题组等情形；A/B 对比阅读是同一个单元。没有隔页素材时说明限制，不能让审计报告假装通过。
3. 内部布局以 bp、左上角原点和向下为正；scene文字/图片采用PDF左下角坐标，在边界转换。跨页先保存 `x - old_body_left`，后加新页版心，不能从旧绝对x直接放到新页。
4. `body_grid`、`CHOICE`、`CLOZE_BOX` 的占位与实际绘制一致。光学字距、线宽、ruby/小注偏移有作用，不因小数长就随意取整；普通正文禁止靠压行距修长文。
5. 数值精简只在写出 `scene.json` 时保持既有12位有效数字渲染参数；计算使用原精度。保护负零、大指数、布尔值、整数ID和字符串中的URL/向量命令。`0.999995`、`12.00001bp`、Bezier比例及容差可能改变渲染，不能一律四舍五入。
6. 新角色要在验证层定义支持的块类型和嵌套；不可容纳的内容显式报错，不能静默裁切、删条件、掉选项或循环产生空页。
7. 沿现有入口扩展 `group_opening()`、`render_item()`、`reference_material()` 等，不复制整个组卷循环；组合类只处理职责内块，其余交回公共实现。
8. 新测试使用合成内容覆盖真实行为边界；不把私人题文、未公开题库路径或用户本机字体位置写进公开测试。修改共享逻辑时按 [workflow](workflow.md) 重建六份公开样例并完成视觉验收。

建议的针对性测试命令示例：

```sh
python3 -m unittest discover -s tests -p 'test_spread_alignment.py'
python3 -m unittest discover -s tests -p 'test_reading_linebreaks.py'
```

这些命令只是开发中的快速反馈；共享引擎交付前仍须全套测试和六册回归。字体替换会影响所有测量，不能只看替换字所在一页。纯数值表示优化要验证同源 TeX 参数与最终像素不变；意图改变排版时按问题逐页记录预期变化。

## 更新文档与公共交付

行为或字段改变时同步 SCHEMA、RULE-LAYOUT 和本技能中对应规则；命令改变同步 workflow；验收新增一种真实失败时补检查表及最小有意义的回归用例。公开提交检查差异文件和忽略边界，仅维护 A/B、既有2014样例和通用代码/文档，不能用 `git add -f` 把私有题库或字体带入。独立出卷/私人备份与公开仓库发布分别处理。
