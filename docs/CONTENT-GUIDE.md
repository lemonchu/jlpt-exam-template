# 编辑与制作试卷

先完成 [README 的环境安装](../README.md#生成第一份-pdf)和[字体配置](FONTS.md)。以下命令从仓库根目录运行；已有题库、蓝图或字体配置应直接复用，避免覆盖自己的修改。

## 1. 准备题库

复制 `content/paper-b/` 为 `content/my-exam/`，修改 V/G/R/L YAML 中的内容。它们分别对应词汇、文法、阅读和听力。保留 schema、题型与必要字段；修改题干、选项、篇章、注音、出处及引用素材。内部 ID 用于选题，`source_pages` 只记录来源页，不控制输出分页。

自然段使用独立 `paragraph` 块；段落内真正需要换行的地址、称呼或落款可用 YAML 的 `|` 保留换行。不要逐行照抄扫描件的自动行末，也不要把不同字段强并成一段。错误选项可能故意拼错，不要自动纠正。

三种注解分开表达：

| 用途 | 输入与位置 |
| --- | --- |
| 振假名 | `｜漢字《かんじ》`；横排字上、竖排字右。明确逐字读音时用 `｜商品《しょう\|ひん》` |
| 正文小注号 | `{{注1\|被注词}}`；横排词下、竖排词左 |
| 释义定义 | 正文之后的独立 `paragraph`，设 `style: small`；在文章框外，读音仍用 ruby |

完整标记例子：

```yaml
- type: box
  blocks:
    - type: paragraph
      text: '｜案内《あん|ない》を{{注1|__確認__}}してください。'
- type: paragraph
  style: small
  text: '（注1）｜確認《かくにん》：よく調べること'
```

下划线用 `__文字__`，粗体用 `**文字**`。解释性括号保留原义，不一概转为读音。完形引用用 `〔41〕` 或 `〔43-a〕`，数字对应关联题的 `source_number`；引擎只重编号明确引用，不修改年份等普通数字。完整字段见 [SCHEMA](SCHEMA.md)。

## 2. 选择蓝图和封面

若沿用默认题组结构，可直接使用默认蓝图。需要选题、换顺序或调整列数时，分别复制 `blueprints/written.yaml`、`blueprints/listening.yaml` 为自定义蓝图。`components_file` 相对蓝图所在目录解析；具体组设置覆盖题型组件设置，题型组件再覆盖 `group_defaults`。

有封面年份或 A/B 标识需求时，复制 `content/common/metadata.yaml` 为 `content/my-exam/metadata.yaml`，再修改对应字段。该文件是整份替代，不能只写两个封面字段。`booklets.written` / `booklets.listening` 下的 `session_label`、`form_symbol` 可留空；非空时需要对应字体，不能从目录名猜 A/B。

复杂材料优先用表格及 `reference` 角色表达，见[信息表材料](RULE-LAYOUT.md#通知与信息表材料reference)。需要题图时放入 `resources/assets/`，用 `asset: assets/文件名` 引用；`alt` 仅作说明，不会修改或生成图像。原文无法确定的内容或竖排方向写进待核对表。

## 3. 分别构建笔试和听力

使用默认蓝图：

```sh
python3 build.py --paper my-exam --booklet written --fonts private/fonts.yaml --output-dir output/my-exam-review
python3 build.py --paper my-exam --booklet listening --fonts private/fonts.yaml --output-dir output/my-exam-review
```

使用自定义蓝图时，分别给两条命令加 `--blueprint blueprints/my-exam-written.yaml`、`--blueprint blueprints/my-exam-listening.yaml`。**更换 `--booklet` 不会替你替换显式指定的蓝图**；不要把笔试蓝图带到听力构建。

其它参数与错误处理见 [CLI 参考](SCHEMA.md#生成模式与错误处理)。不同轮次使用独立输出目录，保存旧 PDF 作为基准。不要在生成的 `content.generated.tex` 或 `selected-content.yaml` 中做永久编辑。

## 4. 检查并交付

确认本次进程成功、`build-report.json` 中 `compiled: true`，再打开输出根目录的 `N1-my-exam-written.pdf` / `N1-my-exam-listening.pdf`。`--no-compile` 可能留下旧的顶层 PDF，报告出现 `PASS` 也不代表本次完成编译或视觉检查。

核对选题和编号，逐页查看正文、题目、图表和注音；页码、正常行距、跨页左起与花纹隔页、续页接题、下划线和注释的检查细节统一见 [PDF 验收清单](../.agents/skills/jlpt-typeset/references/quality-checks.md)。修复后重新编译，不能仅修改源文件就报“已解决”。

交付清楚命名的最终 PDF、用户需要的可编辑源与复现命令，并填写[验收报告](../.agents/skills/jlpt-typeset/assets/qa-report-template.md)，分开记录已编译、已目视和仍需查原文的事项。输出中的 `inputs/` 会归档题库全部 YAML，字体配置和报告也可能含本机路径；不要直接把整个工程当作公共发布包。

新增题库、蓝图、完整字体与输出默认由 `.gitignore` 排除；公共样例范围仍是 A/B 与既有 2014-12。各方素材权利见[第三方说明](../THIRD_PARTY_NOTICES.md)。
