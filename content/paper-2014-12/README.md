# 2014 年 12 月 N1 试排内容

据 `N1 12-2014.pdf`（13页）OCR并对照整理：文字卷70题，听力15道印刷选择题及无印刷题目说明，不含音频和答案。仅供试排与校对，不是官方电子题库。

## 编辑与构建

- `V.yaml`：词汇问题 1–4。
- `G.yaml`：语法问题 5–7，含排序例题和完形材料。
- `R.yaml`：阅读问题 8–13，含问题 11 的 A/B 文本框和问题 13 的两张文字表格。
- `L.yaml`：听力问题 1–5。

按 [README](../../README.md#生成第一份-pdf) 安装依赖并确认 `xelatex`、`xdvipdfmx` 可用。本套含缺字，且启用封面年份与 A/B 圈标；先按[字体说明](../../docs/FONTS.md)配置 Ryumin、FutoGo B101、Gothic MB101 Pro R、New Century Schoolbook Roman（或 C059 Roman），再于根目录执行：

```sh
python3 build.py --paper paper-2014-12 --booklet written --blueprint blueprints/2014-12-written.yaml --fonts private/fonts.yaml
python3 build.py --paper paper-2014-12 --booklet listening --fonts private/fonts.yaml
```

成品：`output/rules/N1-paper-2014-12-written.pdf`、`output/rules/N1-paper-2014-12-listening.pdf`。上述 `private/fonts.yaml` 需先自行配置；`--output-dir` 可改输出根目录。

不需构建也可直接查看仓库 [笔试示例](../../examples/N1-paper-2014-12-written.pdf) / [听力示例](../../examples/N1-paper-2014-12-listening.pdf)。两份PDF不会随构建自动覆盖；分页行为见[排版说明](../../docs/RULE-LAYOUT.md)。

## 排版与校对范围

- A4 模板含封面及背纹，不保证与原始13页或旧展示版相同分页。
- 问题11的 A/B 框按内容计算高度；材料单页时问题另起页，材料已跨页时允许在末页直接接题。
- 问题13为左页问题、右页可编辑日程表；说明相应改为“右のページ”。
- 信息材料采用 `reference` 样式统一标题、说明和表格；属于编辑重排，不宣称复原原卷版式。
- 跨页材料从左页开始，必要时补花纹隔页；笔试保留 A 圈标，听力保留 B 圈标。
- 题号、选项、下划线及主要 OCR 错字已对照整理，全半角和题型说明按模板统一。

正式使用前仍须逐题校对。构建校验只能核对 YAML 到 PDF，不能证明 OCR 无误。

## 听力例题补齐

问题 1、2 借用 A/B 样题的 `L1-example`、`L2-example` 作为练习，各一题；它们不是本年度原卷转录。标记 `is_example: true`，不占正式题号，也不沿用A卷的来源页码。正式印刷选择题仍为15道。问题 3、4 保留无印刷题目的说明与备忘区，问题 5 不设练习。
