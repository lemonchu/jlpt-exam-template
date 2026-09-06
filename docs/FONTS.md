# 字体说明

**现有 A/B 两套题无需下载字体即可编译。** 仓库包含 82 个原稿字形子集，以及两套题需要的少量 Ryumin / FutoGo 补充字形；不提供完整字体，不使用其他字族代替。

## 内置字形

- `profiles/n1-original/fonts/`：原稿已有字形，保留原轮廓与度量。
- `profiles/n1-original/fonts/samples/`：从对应现代字体中提取现有题目及排版所需的少量补充字形，不是完整字库。

日常构建读取仓库中的 YAML、版式与字体子集，不需要原始试卷 PDF。

## 自编题目：补齐新字

写入内置子集未收录的字符时，构建会提示缺少哪个字、应配置哪款字体。在根目录 `fonts.yaml` 的 `faces` 中填写对应本地文件路径即可；只需配置缺字涉及的字体，不必一次找齐全部五款。

| 原字体名称 | 此前选用的完整字体 |
| --- | --- |
| `Ryumin-regular` | A-OTF Ryumin Pr6 R-KL |
| `FutoGoB101-Bold` | A-OTF Futo Go B101 Pr6 Bold |
| `ShinGo-regular` | A-OTF Shin Go Pro R |
| `ShinGo-Bold` | A-OTF Shin Go Pro B |
| `GothicMB101-Bold` | A-OTF Gothic MB101 Pro B |

例如，将自己取得的 Ryumin 字体放在 `resources/user-fonts/ryumin.otf`：

```yaml
schema_version: 1
fonts:
  cover_session: null
  cover_symbol: null
faces:
  Ryumin-regular: resources/user-fonts/ryumin.otf
  FutoGoB101-Bold: null
  ShinGo-regular: null
  ShinGo-Bold: null
  GothicMB101-Bold: null
```

路径相对于项目根目录，也支持绝对路径。可用 `python3 build.py --fonts /path/to/my-fonts.yaml ...` 指定独立配置。字体不需要安装到操作系统；完整字体目录不会提交到 Git。

可在 [ufonts.com](https://ufonts.com/) 搜索上表名称。**非广告、无赞助、无返佣。** 该网站仅作为查找线索，不保证文件就是原稿历史版本，也不代表已获得使用或分发许可。请核对内部字体名称、字重及许可。

## 封面年份与题册符号

只有元数据填写了 `session_label` 或 `form_symbol` 时，才需要配置相应的封面字体：

| 配置键 | 精确字体 | 行为 |
| --- | --- | --- |
| `fonts.cover_session` | A-OTF Gothic MB101 Pro R（PostScript 名 `GothicMB101Pro-Regular`） | 固定施加 `FakeBold=1.5`，接近扫描件中的年份字重 |
| `fonts.cover_symbol` | New Century Schoolbook Roman Regular（PostScript 名 `NewCenturySchlbk-Roman`） | 只绘制 A/B；外圈由模板单独画成细线圆 |

年份应写成全角形式，例如 `（２０２３－２）`。`cover_session` 需要 R 字重文件；若传入 M 或 B，构建会拒绝，以免在较粗的实体字重上继续叠加 `FakeBold`。同字号对照 2023 扫描件后，R + `FakeBold=1.5` 的竖笔粗细最接近；M 略粗，B 明显过粗。三者的全角年份字符字宽相同，因此这一选择不影响居中位置。封面字体内部名称不吻合时会在 `render-report.json` 中提示。若没有 New Century Schoolbook，可使用度量兼容的自由字体 C059 Roman；Fontconfig 将 C059 映射到 New Century Schoolbook，URW Base35 上游以 AGPLv3 加字体嵌入例外发布它。

```yaml
schema_version: 1
fonts:
  cover_session: /path/to/a-otf-gothic-mb101-pro-r.otf
  cover_symbol: /path/to/newcenturyschlbk-roman-regular.ttf
faces:
  Ryumin-regular: null
  FutoGoB101-Bold: null
  ShinGo-regular: null
  ShinGo-Bold: null
  GothicMB101-Bold: null
```

参考：[森泽 Gothic MB101 R 介绍](https://www.morisawa.co.jp/fonts/specimen/1204)与[官方家族样张 PDF](https://resources.morisawa.co.jp/uploads/ung/font_family/set_sample_file/32/GothicMB101_Family.pdf)、[Morisawa 桌面字体许可](https://policies.morisawafonts.com/eula/fonts/desktop/)、[Fontconfig 的 New Century Schoolbook/C059 对应关系](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/raw/main/conf.d/30-metric-aliases.conf)、[URW Base35 许可](https://github.com/ArtifexSoftware/urw-base35-fonts/blob/master/LICENSE)。Morisawa 与用户自行提供的 New Century Schoolbook 字体不会随仓库分发；请自行确认使用和嵌入许可。生成工程直接引用配置的本机路径，`xdvipdfmx` 在最终 PDF 内嵌入所需字形，不另存一份可发布的字体文件。因此中间 LaTeX 工程仍依赖本机字体路径，最终 PDF 则可独立查看和打印。字体路径可含空格和下划线，但不能含 TeX 控制字符 `# % { } \\ $ & ^ ~`。

## 版本差异

项目保留原稿已有字形，以对应的现代完整字体补充新字符。旧版 CID 字体与现代 OpenType 版本可能存在细微轮廓差异，即使商品名和字宽一致，也不能保证逐点相同。FutoGo、ShinGo 和 Gothic MB101 是不同字体，不能相互替代缺字。

## 字体路由与结果检查

优先使用当前科目的原字形，其次使用其他科目同一原字体的字形，再查找同款补充子集，最后使用自己配置的对应完整版。没有可用字形时报告错误；不跨原字体补字。

实际字体使用情况记录在输出目录的 `render-report.json`；封面字体的内部名称、文件摘要和 `FakeBold` 设置也会写入其中。更改字体版本或新增内容后，应检查生成 PDF 的字形和排版。
