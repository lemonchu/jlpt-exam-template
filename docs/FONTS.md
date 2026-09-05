# 字体说明

**现有 A/B 两套题无需下载字体即可编译。** 仓库包含 82 个原稿字形子集，以及两套题需要的少量 Ryumin / FutoGo 补充字形；不提供完整字体，不使用其他字族代替。

## 内置字形

- `profiles/n1-original/fonts/`：原稿已有字形，保留原轮廓与度量。
- `profiles/n1-original/fonts/samples/`：从此前使用的对应现代字体中提取现有题目及其排版所需的少量补充字形；不是完整字库，也不把这些现代字形称为旧版原字形。

原版恢复数据见 `font-reconstruction.json`；补充子集的来源、字符范围与校验值见同目录的 `sample-fonts.json`。

日常构建读取仓库中的 YAML、版式与字体子集，不需要原始试卷 PDF。可运行 `python3 tools/prepare_fonts.py --check` 检查原版子集。

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
faces:
  Ryumin-regular: resources/user-fonts/ryumin.otf
  FutoGoB101-Bold: null
  ShinGo-regular: null
  ShinGo-Bold: null
  GothicMB101-Bold: null
```

路径相对于项目根目录，也支持绝对路径。可用 `python3 build.py --fonts /path/to/my-fonts.yaml ...` 指定独立配置。字体不需要安装到操作系统；完整字体目录不会提交到 Git。

可在 [ufonts.com](https://ufonts.com/) 搜索上表名称。**非广告、无赞助、无返佣。** 该网站仅作为查找线索，不保证文件就是原稿历史版本，也不代表已获得使用或分发许可。请核对内部字体名称、字重及许可。

## 可选：恢复原版子集

仓库已附带原版子集，正常使用无需执行恢复。如果本地文件丢失或需要复核，可以从此前完整项目导入：

```bash
python3 tools/prepare_fonts.py --from-project /path/to/n1-refined-template
```

也可从第一版原始 PDF 恢复。输入文件为 `N1V.pdf`、`N1G.pdf`、`N1R.pdf`、`N1L.pdf`，听力文件名 `N1L(1).pdf` 也可识别；第二版扫描图不能提供这些字形。

```bash
python3 tools/prepare_fonts.py --pdf-dir /path/to/original-first-version-pdfs
```

恢复工具核对轮廓、Unicode 映射和横向度量；它不下载字体，也不恢复五款完整字库。

## 原稿旧 CID 与现代 OpenType

第一版 PDF 的字体记录包括 `Ryumin-regular`、`FutoGoB101-Bold`、`ShinGo-regular`、`ShinGo-Bold`、`GothicMB101-Bold`。检查原始 CFF 数据得到旧 CID 版本信息；它们不是仅凭现代商品名就能确定完全相同的字体文件。Morisawa 也说明过 [NewCID 替换为 OpenType 时的差异](https://mp-support.morisawa.co.jp/hc/ja/articles/28443087810713-NewCID%E3%82%92OpenType%E3%81%AB%E7%BD%AE%E3%81%8D%E6%8F%9B%E3%81%88%E3%81%9F%E3%82%89%E3%81%A9%E3%81%86%E3%81%AA%E3%82%8B)。

前期比较得到：

- Ryumin 的 Regular 比 Light、Medium 更接近原稿。991 个共同字符中，990 个字宽相同；字宽相同并不意味着轮廓相同。
- “日”的局部轮廓有约 1–2/1000 em 的变化；Ryumin ASCII“0”的顶部坐标从旧字形的 718 变为现代完整字体的 749，字宽仍为 500。
- FutoGo、ShinGo 和 GothicMB101 也有旧版与新版的差异。FutoGo、ShinGo、GothicMB101 是不同字体，不能相互充当缺字替代。
- Pr6、Pr6N、Pro 的字符集和异体字支持不同；切换这些后缀或字形特性不能保证还原旧 CID 的全部轮廓。已找到的现代完整版均不能据此宣称为原稿同一历史版本。

因此这里保留原稿已有字形，以所选完整版补充新增字符。模板不会通过人为加粗、换用其他字族或更改题目文字来掩盖缺字。

## 字体路由与结果检查

优先使用当前科目的原字形，其次使用其他科目同一原字体的字形，再查找同款补充子集，最后使用自己配置的对应完整版。没有可用字形时报告错误；不跨原字体补字。

实际字体使用情况记录在输出目录的 `render-report.json`。更改字体版本或新增内容后，应检查生成 PDF 的字形和排版。
