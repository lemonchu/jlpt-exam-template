# 字体说明

**默认规则版即使处理未修改的 A/B，也可能需要完整字体。** 例如 A 文字卷的「謎」需要配置 `Ryumin-regular`；原稿专用字形不能自动用于任意正文角色。缺字会明确报错，不跨原字族替代。

## 内置字形

- `profiles/n1-original/fonts/`：82个原稿子集，保留原轮廓与度量。
- `profiles/n1-original/fonts/samples/`：同款现代字体的少量补充字形。

这些都不是完整字库。日常构建不需要原始试卷 PDF；项目也不分发完整字体。

## 配置完整字体与补齐新字

按缺字提示，在根目录 `fonts.yaml` 的 `faces` 填写对应本地 OTF/TTF 路径；只需配置实际缺字涉及的字体。

| `faces` 键（原字体名称） | 对应完整字体或用途 |
| --- | --- |
| `Ryumin-regular` | A-OTF Ryumin Pr6 R-KL |
| `FutoGoB101-Bold` | A-OTF Futo Go B101 Pr6 Bold |
| `ShinGo-regular` | A-OTF Shin Go Pro R |
| `ShinGo-Bold` | A-OTF Shin Go Pro B |
| `GothicMB101-Bold` | A-OTF Gothic MB101 Pro B |
| `MidashiGo-MB31` | 通知标题；A 的所需字形已内置 |
| `ShinMGo-regular` | 参考资料品牌行；A 的所需字形已内置 |

其他 `faces` 键须与原稿字体目录一致，且字族、字重兼容；通知和参考资料的新字也需对应完整字体。

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

路径相对项目根目录或为绝对路径；`--fonts /path/to/my-fonts.yaml` 指定独立配置。字体无需安装到系统，完整字体目录不提交 Git。路径可含空格、下划线，不能含 TeX 控制字符 `# % { } \\ $ & ^ ~`。

可在 [ufonts.com](https://ufonts.com/) 按名称查找。**非广告、无赞助、无返佣。** 仅作线索，不保证历史版本或授权；请核对内部字体名、字重及使用/分发许可。

## 封面年份与题册符号

仅当元数据 `session_label` 或 `form_symbol` 非空时需要相应字体；字段格式见[SCHEMA.md](SCHEMA.md#公共元数据)。

| 配置键 | 精确字体 | 行为 |
| --- | --- | --- |
| `fonts.cover_session` | A-OTF Gothic MB101 Pro R（PostScript 名 `GothicMB101Pro-Regular`） | 固定施加 `FakeBold=1.5`，接近扫描件中的年份字重 |
| `fonts.cover_symbol` | New Century Schoolbook Roman Regular（PostScript 名 `NewCenturySchlbk-Roman`） | 绘制圈内字母；外圈是独立细线圆 |

年份使用全角，如 `（２０２３－２）`。模板固定选择 **R + `FakeBold=1.5`**：对照扫描件时 M 略粗、B 过粗；三者全角字宽相同。传入 M/B 会被拒绝，避免重复加粗；内部字体名不匹配会写入报告。

New Century Schoolbook 可用度量兼容的 **C059 Roman** 自由替代；Fontconfig 有对应映射，URW Base35 以 AGPLv3 加字体嵌入例外发布。将上述配置的 `fonts` 替换为：

```yaml
fonts:
  cover_session: /path/to/a-otf-gothic-mb101-pro-r.otf
  cover_symbol: /path/to/newcenturyschlbk-roman-regular.ttf
```

字形参考：[森泽 Gothic MB101 R](https://www.morisawa.co.jp/fonts/specimen/1204)、[官方样张](https://resources.morisawa.co.jp/uploads/ung/font_family/set_sample_file/32/GothicMB101_Family.pdf)、[Fontconfig 对应关系](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/raw/main/conf.d/30-metric-aliases.conf)。许可：[Morisawa 桌面字体](https://policies.morisawafonts.com/eula/fonts/desktop/)、[URW Base35](https://github.com/ArtifexSoftware/urw-base35-fonts/blob/master/LICENSE)。用户自备的 Morisawa/New Century Schoolbook 不随仓库分发，使用与嵌入权限须自行确认。

工程引用本机字体路径；`xdvipdfmx` 只在 PDF 嵌入所需字形，不另存可发布的字体文件。中间 LaTeX 工程仍依赖本机字体，最终 PDF 可独立查看和打印。

## 路由与检查

字形优先级：当前科目原字形 → 其他科目同款子集 → 同款补充子集 → 配置的对应完整版。没有可用字形则报错。FutoGo、ShinGo、Gothic MB101 不可互相补字；同名现代 OpenType 与旧 CID 字体也可能有细微轮廓差异。

检查工程的 `render-report.json`（例如 `output/rules/paper-a-written/render-report.json`）：含实际字体、封面内部字体名、文件摘要和 `FakeBold` 设置。更换字体或新增文字后仍须目视检查 PDF。其他模式与输出目录见[构建参数](SCHEMA.md#生成模式与错误处理)。
