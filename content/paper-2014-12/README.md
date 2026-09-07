# 2014 年 12 月 N1 试排内容

据 `N1 12-2014.pdf`（13页）OCR并对照整理：文字卷70题，听力15道印刷选择题及无印刷题目说明，不含音频和答案。仅供试排与校对，不是官方电子题库。

## 编辑与构建

- `V.yaml`：词汇问题 1–4。
- `G.yaml`：语法问题 5–7，含排序例题和完形材料。
- `R.yaml`：阅读问题 8–13，含问题 11 的 A/B 文本框和问题 13 的两张文字表格。
- `L.yaml`：听力问题 1–5。

安装依赖并确保 `xelatex` 在 `PATH` 中。本套含缺字，且启用封面年份与 A/B 圈标；先按[字体说明](../../docs/FONTS.md)配置 Ryumin、FutoGo B101、Gothic MB101 Pro R、New Century Schoolbook Roman（或 C059 Roman），再于根目录执行：

```sh
python3 build.py --paper paper-2014-12 --booklet written --blueprint blueprints/2014-12-written.yaml
python3 build.py --paper paper-2014-12 --booklet listening
```

成品：`output/rules/N1-paper-2014-12-written.pdf`、`output/rules/N1-paper-2014-12-listening.pdf`。默认读取 `fonts.yaml`，可用 `--fonts /path/to/my-fonts.yaml` 指定字体配置、`--output-dir` 改输出目录。字体无需安装到系统，也不提交 Git。

默认使用规则版，`examples/` 保存已验证的规则版展示成品，不自动覆盖。旧模式与分页边界见[排版说明](../../docs/RULE-LAYOUT.md)。

## 排版与校对范围

- A4 模板含封面及背纹，不保证与原始13页或旧展示版相同分页。
- 问题11的 A/B 框按内容计算高度，问题另起页。
- 问题13为左页问题、右页可编辑日程表；说明相应改为“右のページ”。
- 题号、选项、下划线及主要 OCR 错字已对照整理，全半角和题型说明按模板统一。

正式使用前仍须逐题校对。构建校验只能核对 YAML 到 PDF，不能证明 OCR 无误。
