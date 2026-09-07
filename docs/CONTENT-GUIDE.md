# 命题编辑步骤

1. 复制 `content/paper-b/` 到新的英文目录名，例如 `content/my-exam/`。
2. 修改 V/G/R/L YAML 中的题干、四个选项、阅读材料及注音。ID只需在本套内唯一；`source_pages` 仅供校对，不控制输出页。
3. 复制 `blueprints/written.yaml` 或 `listening.yaml` 成自己的蓝图。按需要改变 `groups` 顺序，或用 `items` 选题。蓝图中的 `components_file` 是相对于蓝图文件的路径。
4. 先按[字体说明](FONTS.md)在 `fonts.yaml` 配置所需完整字体，再运行 `python3 build.py --paper my-exam --booklet written --blueprint blueprints/custom.yaml`。默认使用规则排版，打开 `output/rules/N1-my-exam-written.pdf` 逐页检查；听力改用 `--booklet listening`。
5. 检查 `output/rules/my-exam-written/render-report.json`。默认 A/B 和自编内容都可能需要完整字体；缺字按提示配置，不会自动换字族。`--fonts other-fonts.yaml` 可指定独立字体配置。

默认即规则排版，`--rules` 是别名；`--output-dir` 指定产物目录。详见[排版说明](RULE-LAYOUT.md)。

封面年份与圈标在元数据 `booklets.written` 或 `booklets.listening` 下选填 `session_label: "（２０２３－２）"`、`form_symbol: A`；省略、`null` 或空字符串时不绘制。字段见[SCHEMA.md](SCHEMA.md#公共元数据)，对应字体见[FONTS.md](FONTS.md)。

题型：四选一 `choice`、排序 `word_order`、公共材料 `reading`/`cloze`、听力 `listening_choice`/`listening_compound`/`listening_memo`。字段见[SCHEMA.md](SCHEMA.md)。

## 行内格式

```yaml
prompt: 彼の__｜判断《はんだん》__は正しかった。
text: これは{{注1|｜花弁《かべん》}}についての説明である。
```

注音写实际读音；不要把正文换行照搬成每行一个段落。错误选项本来就可能拼写不正确，应保存命题人希望印出的原文。

完形数字引用是 `〔41〕`，配对引用是 `〔43-a〕`、`〔43-b〕`。它们会生成方框，重编号时只更新这些明确引用，不改变年份等普通数字。

最后的复杂材料可在 `resources/assets/` 保存独立 PDF/PNG/JPEG，再修改 `asset`。`alt` 字段仅是说明；要改广告图中文字，应先改素材。

## 验证编辑真实生效

默认工程目录为 `output/rules/<题库>-<题册>/`：`selected-content.yaml` 记录选题和编号，`build-report.json` 记录排版模式与组件。文字来自当前 YAML；缺字段、未闭合标记或材料超限会报错。修改 `content.generated.tex` 不会保留到下次构建。
