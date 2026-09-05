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
faces:
  Ryumin-regular: resources/user-fonts/ryumin.otf
  FutoGoB101-Bold: null
  ShinGo-regular: null
  ShinGo-Bold: null
  GothicMB101-Bold: null
```

路径相对于项目根目录，也支持绝对路径。可用 `python3 build.py --fonts /path/to/my-fonts.yaml ...` 指定独立配置。字体不需要安装到操作系统；完整字体目录不会提交到 Git。

可在 [ufonts.com](https://ufonts.com/) 搜索上表名称。**非广告、无赞助、无返佣。** 该网站仅作为查找线索，不保证文件就是原稿历史版本，也不代表已获得使用或分发许可。请核对内部字体名称、字重及许可。

## 版本差异

项目保留原稿已有字形，以对应的现代完整字体补充新字符。旧版 CID 字体与现代 OpenType 版本可能存在细微轮廓差异，即使商品名和字宽一致，也不能保证逐点相同。FutoGo、ShinGo 和 Gothic MB101 是不同字体，不能相互替代缺字。

## 字体路由与结果检查

优先使用当前科目的原字形，其次使用其他科目同一原字体的字形，再查找同款补充子集，最后使用自己配置的对应完整版。没有可用字形时报告错误；不跨原字体补字。

实际字体使用情况记录在输出目录的 `render-report.json`。更改字体版本或新增内容后，应检查生成 PDF 的字形和排版。
