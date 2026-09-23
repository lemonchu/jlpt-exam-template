# 字体配置

仓库附带原稿字体子集与少量同款补充字形，**不是完整字库**。即使未改 A/B，也可能缺少某个正文角色需要的字，例如 A 笔试的「謎」。缺字会报错，不自动跨字族替换；仅浏览 `examples/` 无需配置字体。

## 先配置实际需要的字体

将根目录 `fonts.yaml` 复制到已忽略的 `private/fonts.yaml`，把需要的 `null` 改成自己的完整字体文件路径，然后用 `--fonts private/fonts.yaml` 构建。已有私人配置直接复用；默认不带 `--fonts` 时仍读取根目录 `fonts.yaml`。

| 配置项 | 对应字体/用途 | 何时需要 |
| --- | --- | --- |
| `faces.Ryumin-regular` | Ryumin Regular，如 A-OTF Ryumin Pr6 R-KL | 正文出现子集未覆盖的字 |
| `faces.FutoGoB101-Bold` | Futo Go B101 Bold，同字族字重的完整字体 | 题干/选项等对应角色缺字 |
| `faces.ShinGo-regular`、`ShinGo-Bold` | Shin Go R / B | 对应角色缺字 |
| `faces.GothicMB101-Bold` | Gothic MB101 Pro B | 对应角色缺字 |
| `faces.MidashiGo-MB31`、`ShinMGo-regular` | 通知标题、参考资料品牌行 | 新材料超出内置字形时 |
| `fonts.cover_session` | Gothic MB101 Pro R，内部名 `GothicMB101Pro-Regular` | metadata中的session_label非空 |
| `fonts.cover_symbol` | New Century Schoolbook Roman，或度量兼容的 C059 Roman | metadata中的form_symbol非空 |

先看错误中的原字体名和角色，只补实际需要的字族；其它 `faces` 键以 `profiles/n1-original/font-catalog.json` 的原名为准。不同 Pro/Pr5/Pr6 版本可能存在轮廓差异，不需要把所有版本都准备一份。

例如自备 Ryumin 放在 `resources/user-fonts/ryumin.otf` 时，私人配置可写：

```yaml
schema_version: 1
fonts:
  cover_session: null
  cover_symbol: null
faces:
  Ryumin-regular: resources/user-fonts/ryumin.otf
```

这只是配置结构示例，不承诺仅此字体能覆盖任意试卷。含年份和圈标时，另填写两个封面字体路径。封面字段定义见 [SCHEMA](SCHEMA.md#公共元数据)。

## 路径与版本

- 使用单独的 `.otf` / `.ttf` 字体文件；不能直接传 `.ttc` / `.otc` 字体集合。
- 相对字体路径从**仓库根目录**解析，不是从配置文件目录解析；绝对路径也可用。
- 无需把字体安装进系统。路径可含空格，但不能含 TeX 控制字符 `# % { } \\ $ & ^ ~` 或控制码。
- 年份字体固定使用 R 并加 `FakeBold=1.5`；传入中/粗体会被拒绝，避免再次加粗。圈内字母与外圈分开绘制；内部名称不匹配的警告会记入报告。
- 完整字体不随项目发布。请从可用的授权来源取得，按实际用途核对使用与嵌入许可；不要把个人字体路径提交到公开配置。

参考：[Gothic MB101](https://www.morisawa.co.jp/fonts/specimen/1204)、[Fontconfig对应关系](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/raw/main/conf.d/30-metric-aliases.conf)、[Morisawa字体许可](https://policies.morisawafonts.com/eula/fonts/desktop/)、[URW Base35许可](https://github.com/ArtifexSoftware/urw-base35-fonts/blob/master/LICENSE)。

## 检查结果与排错

字形路由为当前科目原字形 → 其它科目同款子集 → 同款补充子集 → 配置的对应完整版。FutoGo、ShinGo、Gothic MB101 不可相互补字。更换字体会影响测量和分页，必须重新看实际PDF。

| 现象 | 处理 |
| --- | --- |
| 找不到配置或字体文件 | 核实际路径、外置盘挂载及相对路径基准；不要删字绕过错误 |
| 缺少某字 | 按提示补相应faces项；不要假定现有A/B或装过日文字体就够用 |
| 年份过粗或被拒绝 | 检查是否误用了Gothic MB101的M/B字重 |
| 配置修改后成品没变 | 确认命令用了该--fonts、实际完成编译，并打开本轮输出而非旧PDF |

工程内 `render-report.json` 包含实际字体、内部名称、文件摘要和警告；最终PDF仍须检查缺字、字形及嵌入。TeX工程引用本机字体路径，重新编译仍需原文件；已生成的PDF可独立查看和打印。完整产物说明见 [SCHEMA](SCHEMA.md#输出文件)。
