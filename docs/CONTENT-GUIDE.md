# 命题编辑步骤

1. 复制 `content/paper-b/` 到新的英文目录名，例如 `content/my-exam/`。
2. 修改 V/G/R/L YAML 中的题干、四个选项、阅读材料及注音。ID只需在本套内唯一；`source_pages` 仅供校对，不控制输出页。
3. 复制 `blueprints/written.yaml` 或 `listening.yaml` 成自己的蓝图。按需要改变 `groups` 顺序，或用 `items` 选题。蓝图中的 `components_file` 是相对于蓝图文件的路径。
4. 运行 `python3 build.py --paper my-exam --booklet written --blueprint blueprints/custom.yaml`，打开生成PDF逐页检查。听力改用 `--booklet listening`。
5. 确认字体报告。现有 A/B 内容可使用内置字形直接编译。新字超出内置范围时，在 `fonts.yaml` 中配置对应完整版，并查看 `render-report.json` 确认字体；本版不注册通用替代字体，最终缺字会报错。`--fonts other-fonts.yaml` 可指定自己的同名字体路径。

普通四选一用 `kind: choice`；排序题用 `word_order`。共用文章及其问题用 `reading` 或 `cloze`；听力用 `listening_choice`、`listening_compound`、`listening_memo`。格式和所有主要参数见 `SCHEMA.md`。

## 行内格式

```yaml
prompt: 彼の__｜判断《はんだん》__は正しかった。
text: これは{{注1|｜花弁《かべん》}}についての説明である。
```

注音写实际读音；不要把正文换行照搬成每行一个段落。错误选项本来就可能拼写不正确，应保存命题人希望印出的原文。

完形数字引用是 `〔41〕`，配对引用是 `〔43-a〕`、`〔43-b〕`。它们会生成方框，重编号时只更新这些明确引用，不改变年份等普通数字。

最后的复杂材料可在 `resources/assets/` 保存独立 PDF/PNG/JPEG，再修改 `asset`。`alt` 字段仅是说明；要改广告图中文字，应先改素材。

## 验证编辑真实生效

查看输出目录 `selected-content.yaml` 确认选题和编号，查看 `build-report.json` 确认哪些组件重新排版，再打开PDF检查。构建没有读取旧题文字的兜底；字段缺失、标记未闭合或材料超出约束会报错。不要直接修改 `content.generated.tex` 后期待下次 YAML 构建保留它。
