# JLPT N1 Exam Template

**用 YAML 编辑题目，用同一套 LaTeX 模板生成接近原稿的 N1 试卷。**

仓库保留 A、B 两套样题和 2014 年 12 月试排样例，可生成文字·語彙、文法、読解与听力题册；听力不含音频。题目与版式分开保存，支持替换内容、自定义组卷。

公开仓库仅维护上述样例及可复用的排版引擎。其它本机题库、年度卷素材、导入记录和生成成品不纳入发布；试题及引用材料不受代码许可覆盖。

先看效果：[仓库示例 PDF](https://github.com/lemonchu/jlpt-exam-template/tree/main/examples) · [JLPT 官方样板](https://www.jlpt.jp/samples/sampleindex.html)。六份仓库示例由默认规则版生成；本项目与 JLPT 官方无关联。

## 快速开始

安装 **Python 3.10+** 和带有 XeLaTeX 的 **TeX Live / MacTeX**，然后安装项目依赖：

```bash
git clone https://github.com/lemonchu/jlpt-exam-template.git
cd jlpt-exam-template
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

按[字体说明](docs/FONTS.md)配置 `fonts.yaml`，然后构建。**仓库仅附带字体子集，即使处理 A/B 也可能需要完整字体**，例如 A 文字卷的「謎」；缺字会报错，不会自动换字体。

```bash
python3 build.py --paper paper-a --booklet written
```

输出：`output/rules/N1-paper-a-written.pdf`。换成 `--paper paper-b` 或 `--booklet listening` 可构建另一题库或听力卷；`--fonts /path/to/my-fonts.yaml` 可指定独立字体配置。

2014 试卷需要额外字体和文字卷蓝图，构建命令见 [2014 说明](content/paper-2014-12/README.md)。

## 使用 AI 排版

仓库提供可复用技能 **`jlpt-typeset`**，入口是 [SKILL.md](.agents/skills/jlpt-typeset/SKILL.md)。包含环境与文件地图、组卷命令、完整工作流、开发模块、逐页验收清单、常见排版问题的修复方法，以及交付报告模板。

在仓库中打开支持本地技能的 Codex，可通过技能选择器选择它；CLI / IDE 也可直接输入：

```text
请使用 $jlpt-typeset，把 content/my-exam 的内容生成笔试和听力 PDF。
使用 private/fonts.yaml；成品放在 output/my-exam-review。
生成后逐页检查版式，并交付验收报告及仍需核实的问题表。
```

`my-exam` 和字体配置需换成自己的文件。其他能够读取仓库、运行命令并查看图像的 AI，也可以直接使用下面的提示，无需特定插件：

```text
请先读取 .agents/skills/jlpt-typeset/SKILL.md，按其中按需引用的工作流和检查表，
帮我完成本次试卷排版。缺少字体或无法进行视觉检查时，请具体说明；
不要把仅生成 TeX、测试通过或旧 PDF 仍存在当成成品验收完成。
```

这是仓库内的技能说明，不会自行启动 AI，也不需要为排版引擎配置 API key。`SKILL.md` 承载可调用的工作流；`AGENTS.md` 通常承载长期项目约定，现有根目录文件用于本机私有记录，不随仓库发布。公开技能不依赖它。技能发现位置和调用方式见 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills)；若客户端未发现技能，可直接提供上面的文件路径。

先查看 [PDF 验收清单](.agents/skills/jlpt-typeset/references/quality-checks.md) 或 [运行与交付流程](.agents/skills/jlpt-typeset/references/workflow.md)。AI 仍须实际编译并查看成品；无法核实的原文和版式必须保留在报告中。

## Windows / Conda

安装 Conda 和 TeX Live，确保 `xelatex`、`xdvipdfmx` 在 PATH 中。在 Conda 终端的仓库根目录执行：

```powershell
conda env create -f environment.yml
conda activate jlpt-exam
python build.py --paper paper-b --booklet written
```

字体配置同上；已有环境只需激活。

## 编辑与组卷

| 想做什么 | 从哪里改 |
| --- | --- |
| 改题目、注音、选项 | `content/<题库>/`；另起一套可复制为 `content/my-exam/`，用 `--paper my-exam` 构建 |
| 调整选题、编号、分页 | `blueprints/`；用 `--blueprint 路径` 指定 |
| 添加可选年份、圆圈 A/B | 元数据中的封面字段；不填则不显示 |
| 放入广告、图表 | YAML 引用独立 PDF、PNG 或 JPEG |

入门见[内容指南](docs/CONTENT-GUIDE.md)，完整字段见 [YAML 参考](docs/SCHEMA.md)。

新增本机题库和蓝图默认不纳入 Git；公开样例范围由 `.gitignore` 的允许列表限定。

## 排版与输出

默认由共享规则排正文，封面和固定排序示范使用独立模板，不套用旧 A 正文坐标。修改内容后，断行与页数可以变化；不承诺与原稿逐像素相同。

跨页阅读材料自动左页起排，必要时补花纹隔页；长文保持正常行距，续页可直接接题。支持正文下方小注、释义振假名和可编辑的信息表材料。生成场景的浮点尾数按既有渲染精度精简，测量与分页计算保留原精度。

`--rules` 是可省略的别名；默认输出到 `output/rules/`，`--output-dir 路径` 可覆盖目录。旧 `--precise`、`--recompose` 已移除。

构建不会更新 `examples/`。规则与限制见[排版规则](docs/RULE-LAYOUT.md)。

## 开发与测试

```bash
python3 -m unittest discover -s tests
```

模块职责、PDF 回归与原稿对照方法见[维护参考](docs/ARCHITECTURE.md)。

## 许可

原创代码使用 [AGPLv3](https://github.com/lemonchu/jlpt-exam-template/blob/main/LICENSE)。试题、引用文章、图像及字体归各自权利人所有，不受代码许可覆盖，见 [第三方说明](https://github.com/lemonchu/jlpt-exam-template/blob/main/THIRD_PARTY_NOTICES.md)。

## 使用与引用

如果这个项目对你有用，公开使用或分享生成结果时，请顺手注明 [jlpt-exam-template](https://github.com/lemonchu/jlpt-exam-template) 的项目来源。它为了把每个字、每条线和每处注音放到合适的位置，真的已经很努力了——别让它干完活以后，连名字都没留下捏。

*I was astonished that GPT-6 made this project possible. It helped turn a difficult layout reconstruction into an editable, reusable exam template.*
