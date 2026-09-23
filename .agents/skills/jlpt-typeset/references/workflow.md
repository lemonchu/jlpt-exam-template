# 文件、配置与出卷流程

本文件中的命令均从仓库根目录运行。`python3` 可换成已激活环境的 `python`；示例路径需换成用户实际文件。只使用当前公开仓库即可执行，不依赖维护者的本机日志或私人工具。

## 文件地图

| 路径 | 用途与编辑边界 |
| --- | --- |
| `build.py` | CLI 入口：读配置、选题、编号、生成场景、编译和归档 |
| `content/common/metadata.yaml` | 公共封面、科目名、页眉页脚、花纹素材等默认元数据 |
| `content/paper-a/`、`paper-b/`、`paper-2014-12/` | 公开样例的 V/G/R/L YAML；分别是词汇、文法、阅读、听力 |
| `blueprints/written.yaml`、`listening.yaml` | 默认组卷顺序、选题、编号及布局意图 |
| `blueprints/components.yaml` | 共享组件配置；2014 笔试另用 `2014-12-written.yaml` |
| `fonts.yaml` | 完整字体配置示例，公开文件不放个人绝对路径；推荐另建私有配置 |
| `resources/assets/` | 引用的 PDF、PNG、JPEG 素材；素材文本不由 `alt` 自动改写 |
| `profiles/n1-original/` | 字体目录、原字形子集、封面/排序示范固定模板与校准数据 |
| `engine/`、`profiles/n1-original/n1-exact.sty` | 语义排版规则与最终 TeX 绘图支持；入口见开发指南 |
| `examples/` | 六份已确认的展示/回归 PDF，构建不会自动更新它们 |
| `tests/` | 合成边界用例、公开样例回归及外观诊断工具 |
| `output/`、`tmp/` | 默认被忽略的产物/临时证据；不要把全部中间文件当交付包 |
| `docs/` | 内容指南、字段、字体、规则和架构的详细文档 |

字段以 [SCHEMA](../../../../docs/SCHEMA.md) 为准；编辑示例见 [CONTENT-GUIDE](../../../../docs/CONTENT-GUIDE.md)。新增题库及蓝图默认不进入公共 Git 允许列表。

## 环境和字体

1. 使用 Python 3.10+，按根目录 `requirements.txt` 安装 PyYAML、fonttools、PyMuPDF。已有合适环境则直接使用，不重复创建。
2. 确认带 XeLaTeX 的 TeX Live / MacTeX 可用，`xelatex`、`xdvipdfmx` 在 PATH。macOS 常见位置 `/Library/TeX/texbin`；Windows 可用 README 的 Conda 流程。
3. 按 [FONTS](../../../../docs/FONTS.md) 配置需要的完整字体。仓库子集不能保证覆盖 A/B，更不能覆盖任意新题文。核对字体文件真实存在、内部名称和字重；不要用“成功找到一个日文字体”替代原字族匹配。

```sh
python3 --version
xelatex --version
xdvipdfmx --version
python3 -m pip install -r requirements.txt
python3 build.py --help
```

推荐把个人配置放到已忽略的 `private/fonts.yaml`，用 `--fonts private/fonts.yaml` 指定。`faces` 配正文补字，`fonts.cover_session` 配年份，`fonts.cover_symbol` 配圈内字母；相对字体路径是**相对仓库根目录**，不是相对配置文件。年份/圈标为空时不需要相应封面字体。不要把所有 Pro/Pr5/Pr6 变体一起打包，按最终实际使用字体核对；完整字体分发另受许可限制。

## 命令速查

下面的 `output/ai-review` 是独立输出根目录示例；复查已有成品时使用新的运行目录，避免覆盖唯一基准。准备好所指字体配置后执行：

```sh
python3 build.py --paper paper-a --booklet written --fonts private/fonts.yaml --output-dir output/ai-review
python3 build.py --paper paper-a --booklet listening --fonts private/fonts.yaml --output-dir output/ai-review
python3 build.py --paper paper-b --booklet written --fonts private/fonts.yaml --output-dir output/ai-review
python3 build.py --paper paper-b --booklet listening --fonts private/fonts.yaml --output-dir output/ai-review
python3 build.py --paper paper-2014-12 --booklet written --blueprint blueprints/2014-12-written.yaml --fonts private/fonts.yaml --output-dir output/ai-review
python3 build.py --paper paper-2014-12 --booklet listening --fonts private/fonts.yaml --output-dir output/ai-review
```

| 参数 | 行为与注意事项 |
| --- | --- |
| `--paper NAME` | 对应 `content/NAME/`；只接受英文字母、数字、下划线和连字符 |
| `--booklet written/listening` | 不可用 `reading` 等科目名代替；未指定默认 written |
| `--blueprint FILE` | 不指定用 `blueprints/<booklet>.yaml`；2014 笔试必须显式选专用蓝图 |
| `--metadata FILE` | 优先级：显式文件 → 题库目录的 metadata → common；选择整份，不逐字段合并 |
| `--fonts FILE` | 不指定时读根目录 `fonts.yaml`；该公开示例可能尚未配置 |
| `--output-dir DIR` | 覆盖输出根目录；默认 `output/rules`，不会再自动追加 `rules` |
| `--no-compile` | 仍执行排版、字体解析和 TeX/报告生成，但不编译 PDF；不是不需要字体的纯语法检查 |
| `--rules` | 默认规则版的可省略别名；旧 `--precise` / `--recompose` 已移除 |

## 完整工作流

### 1. 盘点并保存基准

明确出哪些题册、输入文件、期次与圈标、来源可信程度、交付格式。检查 `git status --short` 和相关文件，避免覆盖用户已有修改。保存改动前的 PDF、构建配置与必要的页数/摘要，标注“基准”，与本轮目录分开；不要依赖历史报告推断当前文件。

批量工作维护本机恢复记录：本轮输入、完成的题册、检查证据、未决项、下一步。中断恢复先读记录，再核实产物；日志与凭据不进入公开交付。并行代理可分题库/审查范围，各用独立输出目录；共享 Python 修改集中合并，避免互相覆盖构建。

### 2. 编辑内容和蓝图

新题库可复制 `content/paper-b/` 为 `content/my-exam/`，保留 YAML schema，再替换成获准使用的内容；不要漏改 ID、选项、出处、注音和图表条件。复制默认蓝图为 `blueprints/my-exam-written.yaml` 后选组/选题；`components_file` 相对蓝图文件所在目录解析。`source_pages` 是来源记录，不控制生成页码。组配置按 `group_defaults` → `components[题型kind]` → 具体 `groups` 条目覆盖；局部设置看似不生效时检查这一优先级。

在题库目录保存完整 `metadata.yaml` 可隔离封面修改。年份 `session_label`、圈标 `form_symbol` 分别填写在 `booklets.written` / `booklets.listening`，内容应有依据，不从目录名猜 A/B。默认公共元数据未填写圈标；需要显示时须明确填写。

行内语法例子（仅为合成格式演示）：

```yaml
text: '｜案内《あん|ない》を{{注1|__確認__}}してください。'
```

自然段不要按扫描件的自动行末硬换行；真实的地址、收件人、落款、表格与段落边界应保留。区分 `style: small` 释义与材料自身注意事项。图像的方向、旋转、裁切和尺寸需检查原素材；竖排不能仅凭文体猜测。

### 3. 试排、实际编译、校对

需要快速诊断布局时可在独立目录先 `--no-compile`。正式交付重新执行不带该参数的命令，记录退出状态，再查本轮 PDF 及报告。`--no-compile` 会清理工程内旧 `main.pdf`，但输出根目录旧 `N1-<paper>-<booklet>.pdf` 可能仍存在；构建失败也可能留下旧报告。不要把遗留文件当本轮结果。

完成 [quality-checks.md](quality-checks.md)。先核语义和自动报告，再查看整页、对页与细节。发现通用问题时改共享规则、补必要的边界测试；发现输入格式错误时改 YAML。每次修复重新生成受影响 PDF，页数改变时重新检查后续单元左右起排和封面总页数。

### 4. 验证范围

- 仅改题文：构建涉及的题册，核对修改处、相邻页和之后的分页；新题册逐页检查。
- 改共享引擎、字体路由、公共蓝图或模板：运行全套单元测试并构建上方六份公开样例；再检查新增内容覆盖不到的长文/长注音/表格等边界。
- 仅改文档或技能说明：核对命令、字段、链接和可用性，不为凑验收记录重编全部 PDF。
- 已确认的视觉改动可更新 `examples/`；先说明变化并验收，不能把失败的回归通过覆盖基准变成成功。

```sh
python3 -m unittest discover -s tests
python3 tests/verify_examples.py --actual-dir output/ai-review --expected-dir examples \
  paper-a-written paper-a-listening paper-b-written paper-b-listening \
  paper-2014-12-written paper-2014-12-listening
```

`verify_examples.py` 默认只比较 A 的两册；六册回归必须显式列出。它比较每页 2 倍栅格像素，不是 PDF 文件字节。意图仅重构/数值精简时要求像素不变；意图改变版式时逐项解释并查看变化页，不能因差分非零就回滚正确修改。

## 产物与报告

以默认输出为例，成品是 `output/rules/N1-paper-a-written.pdf`；工程目录是 `output/rules/paper-a-written/`：

| 文件 | 应核对什么 |
| --- | --- |
| `main.pdf`、`main.tex`、`content.generated.tex` | 实际编译产物与生成工程；TeX 是诊断结果，不是永久编辑入口 |
| `build-report.json` | `compiled`、总页/正文页、组件参数与归档输入摘要；`BUILT` 单独不证明编译或视觉通过 |
| `selected-content.yaml` | 本次真正选入的题文、顺序与重编号结果 |
| `material-spreads.json` | 每个材料单元的正文起止页、跨页和新增隔页；读具体记录，不只看文件存在 |
| `render-report.json` | 实际字体、缺字/封面字体信息和渲染情况；`PASS` 不等于原文或外观正确 |
| `metadata-layout-report.json` | 封面等元数据文字的布局情况 |
| `item-layout.json`、`semantic-ledger.json` | 题目位置与语义追踪的诊断依据，不替代 PDF 文字与图像核对 |
| `scene.json`、`resolved.json` | 场景命令与字形/素材解析；数字简化在输出边界进行 |
| `composition-font-usage.json` | 包含测量阶段的请求字形，不能据此断言所有字体均出现在最终 PDF |
| `inputs/`、`assets/` | 构建归档；inputs会收录该题库目录所有YAML（含本册未用者），可能含私人题源与字体路径，不能整目录公开上传 |

交付默认为成品 PDF、必要的可编辑源/配置/引用素材、复现命令和填写后的 [验收报告](../assets/qa-report-template.md)；按用户范围决定是否附源文件，字体仅给配置要求。多卷可按用户指定的年份/题册组织；文件名必须能辨识卷别，目录中不夹带临时 PNG、TeX、旧版、原始压缩包或无关文件。

报告用“已编译”“已做哪些视觉检查”“哪些来源已核实/仍待核实”分别陈述，列出实际文件、页数和异常。用户要求同步/上传时只同步已验收清单，验证远端回执或可见内容；不把本地成功写成远端成功。
