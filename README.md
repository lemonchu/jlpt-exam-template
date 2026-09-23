# JLPT N1 Exam Template

**用 YAML 编辑题目，生成接近 JLPT 样板风格的 N1 试卷 PDF。**

仓库包含 A、B 两套样题和 2014 年 12 月试排样例，支持笔试与听力题册；听力不含音频。题文和版式分开保存，可以替换内容、自定义组卷。

## 先看效果

浏览 PDF 无需安装环境。以下六份文件由本仓库生成：

| 样例 | 笔试 | 听力 |
| --- | --- | --- |
| A | [查看 PDF](examples/N1-paper-a-written.pdf) | [查看 PDF](examples/N1-paper-a-listening.pdf) |
| B | [查看 PDF](examples/N1-paper-b-written.pdf) | [查看 PDF](examples/N1-paper-b-listening.pdf) |
| 2014 年 12 月 | [查看 PDF](examples/N1-paper-2014-12-written.pdf) | [查看 PDF](examples/N1-paper-2014-12-listening.pdf) |

官方参考：[JLPT 样题](https://www.jlpt.jp/samples/sampleindex.html)。本项目与 JLPT 官方无关联；公开题库限上述样例，其余题库和生成成品不随仓库发布。

## 生成第一份 PDF

需要 **Python 3.10+** 和带有 `xelatex`、`xdvipdfmx` 的 **TeX Live / MacTeX**。macOS / Linux：

```sh
git clone https://github.com/lemonchu/jlpt-exam-template.git
cd jlpt-exam-template
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
mkdir -p private
cp fonts.yaml private/fonts.yaml
```

先按[字体说明](docs/FONTS.md)编辑 `private/fonts.yaml`，填入所需完整字体的路径。**仓库只附带子集，即使构建 A/B 也可能缺字；配置中的 `null` 不是已就绪字体。** 私人配置放在被 Git 忽略的 `private/`，无需改公开配置或安装系统字体。

```sh
python3 build.py --paper paper-a --booklet written --fonts private/fonts.yaml
```

成品为 `output/rules/N1-paper-a-written.pdf`。换成 `--paper paper-b` 或 `--booklet listening` 可生成另一册。2014 笔试需专用蓝图，见 [2014 说明](content/paper-2014-12/README.md)。

<details>
<summary>Windows / Conda</summary>

安装 Conda、TeX Live，确保 `xelatex`、`xdvipdfmx` 在 PATH。在仓库根目录执行：

```powershell
conda env create -f environment.yml
conda activate jlpt-exam
New-Item -ItemType Directory -Force private
Copy-Item fonts.yaml private/fonts.yaml
```

按上方字体说明编辑配置后，执行 `python build.py --paper paper-a --booklet written --fonts private/fonts.yaml`。已有环境和私人配置直接复用，不必重新复制。

</details>

## 接下来做什么

| 目标 | 阅读入口 |
| --- | --- |
| 换题、加注音、制作自己的试卷 | [内容编辑指南](docs/CONTENT-GUIDE.md) |
| 查 YAML 字段、CLI 参数和输出报告 | [配置参考](docs/SCHEMA.md) |
| 了解分页、注释、竖排和图表规则 | [排版规则](docs/RULE-LAYOUT.md) |
| 检查成品、定位常见排版问题 | [PDF 验收清单](.agents/skills/jlpt-typeset/references/quality-checks.md) |
| 修改引擎、运行回归、准备发布 | [开发与维护](docs/ARCHITECTURE.md) |

构建后须查看实际 PDF。长文按正常行距跨页；默认元数据提供花纹隔页，跨页阅读单元按需左起。页数可随内容变化，`examples/` 不会被构建自动覆盖。

## 使用 AI 排版

仓库内置 **`jlpt-typeset`** 技能，提供操作流程、检查清单和交付报告模板。在支持本地技能的 Codex 中选择它，或在 CLI / IDE 输入：

```text
请使用 $jlpt-typeset，根据本仓库完成试卷排版，检查成品并列出待确认问题。
```

其他具备文件、命令和图像查看能力的 AI，可直接提示“先读取 `.agents/skills/jlpt-typeset/SKILL.md`，再按其流程处理”。[技能入口](.agents/skills/jlpt-typeset/SKILL.md)可直接阅读；无需安装专用插件，也无需为排版引擎设置 API key。技能发现方式见 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills)。

## 许可与引用

原创代码使用 [AGPLv3](LICENSE)。试题、引用文章、图像和字体不受代码许可覆盖，见[第三方说明](THIRD_PARTY_NOTICES.md)。公开使用或分享生成结果时，请注明 [jlpt-exam-template](https://github.com/lemonchu/jlpt-exam-template) 的项目来源。
