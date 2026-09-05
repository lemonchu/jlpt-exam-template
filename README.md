# JLPT N1 Exam Template

**用 YAML 编辑题目，用同一套 LaTeX 模板生成接近原稿的 N1 试卷。**

包含 A、B 两套示例题及一套 2014 年 12 月试排，覆盖文字·语彙、文法、読解和听力题册。内容、题型和版式分开保存：既能生成现有示例，也能替换内容、自定义组卷。听力部分不含音频。

想先了解正式题册的内容与视觉效果，可以查看 [JLPT 官网的《日本語能力試験公式問題集》](https://www.jlpt.jp/samples/sampleindex.html)。本项目是独立模板，与 JLPT 官方无关联。

## 快速开始

安装 **Python 3.10+** 和带有 XeLaTeX 的 **TeX Live / MacTeX**，然后运行：

```bash
git clone https://github.com/lemonchu/jlpt-exam-template.git
cd jlpt-exam-template
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 build.py --paper paper-a --booklet written
```

PDF 输出到 `output/N1-paper-a-written.pdf`。将 `paper-a` 改为 `paper-b` 可生成另一套题；将 `written` 改为 `listening` 可生成听力题册。

**现有 A/B 两套题可直接编译，无需另找字体。** 项目保留原版旧字形子集，并附上现有题目需要的少量补充字形；不改用其他字体，也不提供完整版字体。

## 如何命题

- **改题目**：编辑 `content/paper-a/` 或 `content/paper-b/` 中的 YAML。另起一套时复制为 `content/my-exam/`，构建时使用 `--paper my-exam`。
- **改组卷**：编辑 `blueprints/`，调整题组、选题、编号和纸张边侧的分区标记。
- **放广告或图表**：复杂材料可保存为独立 PDF、PNG 或 JPEG，由 YAML 引用；题干和选项仍是可编辑文字。

字段与示例见 [内容指南](https://github.com/lemonchu/jlpt-exam-template/blob/main/docs/CONTENT-GUIDE.md) 和 [YAML 参考](https://github.com/lemonchu/jlpt-exam-template/blob/main/docs/SCHEMA.md)。生成效果也可直接查看 [`examples/`](https://github.com/lemonchu/jlpt-exam-template/tree/main/examples) 中的 PDF。

## 字体与精度

内置子集只覆盖已有内容。写入未收录的新字时，需要在 `fonts.yaml` 中配置对应的完整字体：Ryumin、FutoGo B101、ShinGo 或 Gothic MB101。缺字会明确报错，不会悄悄换字体。

可自行在 [ufonts.com](https://ufonts.com/) 按名称寻找。**非广告、无赞助、无返佣**；该站仅作为查找线索，请核对字体版本及许可。具体名称和配置见 [字体说明](https://github.com/lemonchu/jlpt-exam-template/blob/main/docs/FONTS.md)。

原稿已有字形保留原轮廓；补充字形取自对应的现代字体版本，局部可能与旧版不同。修改内容或组卷后会重新排版，断行和页数也可能变化。

## 许可

原创代码使用 [AGPLv3](https://github.com/lemonchu/jlpt-exam-template/blob/main/LICENSE)。试题、引用文章、图像及字体归各自权利人所有，不受代码许可覆盖，见 [第三方说明](https://github.com/lemonchu/jlpt-exam-template/blob/main/THIRD_PARTY_NOTICES.md)。

## 使用与引用

如果这个项目对你有用，公开使用或分享生成结果时，请顺手注明 [jlpt-exam-template](https://github.com/lemonchu/jlpt-exam-template) 的项目来源。它为了把每个字、每条线和每处注音放到合适的位置，真的已经很努力了——别让它干完活以后，连名字都没留下捏。

*I was astonished that GPT-6 made this project possible. It helped turn a difficult layout reconstruction into an editable, reusable exam template.*
