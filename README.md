# JLPT N1 Exam Template

**用 YAML 编辑题目，用同一套 LaTeX 模板生成接近原稿的 N1 试卷。**

包含 A、B 和 2014 年 12 月三套题库，可生成文字·语彙、文法、読解与听力题册；听力不含音频。题目与版式分开保存，支持替换内容、自定义组卷。

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

## 编辑与组卷

| 想做什么 | 从哪里改 |
| --- | --- |
| 改题目、注音、选项 | `content/<题库>/`；另起一套可复制为 `content/my-exam/`，用 `--paper my-exam` 构建 |
| 调整选题、编号、分页 | `blueprints/`；用 `--blueprint 路径` 指定 |
| 添加可选年份、圆圈 A/B | 元数据中的封面字段；不填则不显示 |
| 放入广告、图表 | YAML 引用独立 PDF、PNG 或 JPEG |

入门见[内容指南](docs/CONTENT-GUIDE.md)，完整字段见 [YAML 参考](docs/SCHEMA.md)。

## 排版模式

默认由共享规则排正文，封面和固定排序示范使用独立模板，不套用旧 A 正文坐标。修改内容后，断行与页数可以变化；不承诺与原稿逐像素相同。

| 模式 | 行为 | 默认输出目录 |
| --- | --- | --- |
| 无参数或 `--rules` | 当前规则排版 | `output/rules/` |
| `--precise`（已弃用） | 旧精确兼容路径；不兼容时回退旧流排 | `output/precise/` |
| `--recompose`（已弃用） | 旧流排，供迁移对照 | `output/recompose/` |

模式参数互斥；`--output-dir 路径` 可覆盖输出目录。旧版默认行为现在需显式加 `--precise`，仅供回归对照。构建不会更新 `examples/`。规则与限制见[排版规则](docs/RULE-LAYOUT.md)。

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
