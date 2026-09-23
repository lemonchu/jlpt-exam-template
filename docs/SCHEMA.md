# 内容与配置格式，版本 1

内容、蓝图、元数据分开保存。题目中不写字体编号、逐字坐标或分页命令；尺寸放蓝图，备忘区固有 `height` 除外。入门见[内容指南](CONTENT-GUIDE.md)，规则边界见[排版说明](RULE-LAYOUT.md)。

## 试题内容文件

每套内容目录通常含 `V.yaml`、`G.yaml`、`R.yaml`、`L.yaml`：

```yaml
schema_version: 1
section: V
groups:
  - id: V1
    kind: choice
    title: 問題１
    instruction: 最もよいものを一つ選びなさい。
    items:
      - id: V-01
        source_number: 1
        prompt: ここに題干を入力する。
        options: [選択肢一, 選択肢二, 選択肢三, 選択肢四]
```

| 字段 | 约定 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `section` | `V`、`G`、`R` 或 `L` |
| `groups` | 题组列表 |
| 题组 `id` | 唯一字符串，首字母与 `section` 相同 |
| `kind` | 下表中的题型 |
| `title`、`instruction` | 题型标题和说明；支持行内标记 |
| `items` | 该题组的直接题目或篇章列表 |

| `kind` | `items` 的结构 |
| --- | --- |
| `choice` | 四选一题目 |
| `word_order` | 四选一题目；题干保留空位与星号 |
| `listening_choice` | 四选一题目；题干可以为空 |
| `reading`、`cloze` | 公共材料和其关联问题 |
| `listening_compound` | 一组听力公共材料和其关联问题 |
| `listening_memo` | 说明或备忘材料，问题列表可以为空 |

## 行内文字

- `｜漢字《かんじ》`：整词注音。
- `｜商品《しょう|ひん》`：逐字注音；片段数量须等于被注文字的字符数（含假名等非汉字字符），每段非空。不加分隔符则按整词处理，不自动猜读音。
- `__下線__`：下划线；允许 `__｜漢字《かんじ》__`。
- `**太字**`：粗体。
- `（　　　）`：全角填空括号；`__　　　__`：三字空线；`__★__`：同宽星号空线。
- `{{注1|用語}}`：行下小注；可写 `{{注1|｜漢字《かんじ》}}`。数字圆圈下标可写 `{{①|__語句__}}`。
- LF 表示作者要求的明确换行；自然段宜拆为独立 `paragraph`，不保留原 PDF 的任意自动行末。

保留实际标点和命题人希望印出的错误选项。YAML 中以特殊符号开头的字符串应加引号。

## 四选一题目

| 字段 | 必需性与含义 |
| --- | --- |
| `id` | 必填，唯一内部 ID |
| `prompt` | 题干字符串；听力可为 `''` |
| `options` | 恰好四个字符串，不含模板生成的选项编号 |
| `source_number` | 可选来源题号；使用来源编号或完形引用时需要 |
| `source_pages` | 可选来源 PDF 页次列表，从 1 开始，不控制输出分页 |
| `is_example` | 可选布尔值，`true` 表示例题，不计正式自动题号 |
| `label` | 可选显式显示标签，如 `例`、`質問１`；取代自动编号且不推进计数 |
| `stimulus` | 可选附加材料块列表 |
| `stimulus_position` | `after_options` 放选项后；省略时放题干后、选项前 |

`word_order` 使用相同字段；题干保留四空和一星，四个选项是待排序片段。听力自动编号按组重新开始，并加带注音的「番」。

听力选择题也支持 `stimulus` 和 `stimulus_position`，可在选项前后显示图示。材料与选项共同占用该题面板的空间；超出时构建会报错。先检查图片实际尺寸和内容；单个大图题可用下表的 `full_page_items` 独占页，只有整组都需要时才减少 `items_per_page`。不要缩小到难以辨认。

当四个带编号的选项已包含在题图中时，可设置 `options_embedded_in_stimulus: true`，避免重复打印文字选项。此时必须提供 `image` 材料，`options` 仍保留四项文字描述供内容审查；题图中的编号及图形需人工核验。

## 公共材料与关联题

```yaml
- id: G7-passage
  label: （１）
  stimulus:
    - type: paragraph
      text: 文章の中の〔43-a〕と〔43-b〕を考える。
  questions:
    - id: G-43
      source_number: 43
      prompt: ''
      options: [a：一／b：二, a：一／b：三, a：二／b：三, a：三／b：四]
```

篇章含 `id`、`stimulus`、`questions`，可选 `label`、`source_pages`。关联题使用四选一结构；仅有说明或备忘区时可写 `questions: []`，不代表音频题数。

完形引用为 `〔41〕`、`〔43-a〕`、`〔43-b〕`；可选后缀限一个 ASCII 字母。引用数字须对应问题的 `source_number`；重编号只更新引用数字，保留后缀，不改选项中的 a/b 或普通年份。

## 材料块

| `type` | 内容字段与含义 |
| --- | --- |
| `paragraph` | `text`；可选 `style: bold\|small`、`align: left\|center\|right`、非负数 `indent` |
| `heading` | `text`，作为材料标题 |
| `vertical` | `text`，按语义阅读顺序填写的纵排文章 |
| `box` | `blocks`，框内递归材料列表 |
| `table` | `rows` 为二维字符串列表，每行列数相同；`header_rows` 为表头行数，默认 0；可用 `borders: false` 隐藏单元格线，以 `width` 和 `align: left\|center\|right` 控制表格宽度与对齐；`column_widths` 为与列数相同的正数权重列表（不必加和为1），覆盖蓝图中该列数的比例；`column_alignments` 可逐列设置对齐，表头另可用 `header_bold`、`header_fill`、`header_alignments` |
| `image` | `asset` 为 `assets/` 下的相对文件路径；`alt` 为说明或转录，不打印 |
| `memo` | 可选 `label`，默认 `－メモ－`；可选 `height` 为该空白书写区固有高度，单位 bp |
| `separator` | 两部分材料之间的空白间隔 |

图像支持 PDF（第一页）、PNG、JPEG，适合广告或手写材料，不应代替可编辑题干与选项。`alt` 不修改图中文字。

表格列宽、纵排列高、图片位置优先放蓝图。复合听力中未指定 `style` 的段落按作答说明的字号、行距和粗体排版。

`rule_style` 标记引文、对话、通知、图注或参考资料等材料角色，由当前排版规则解释。角色列表、嵌套限制与示例见[排版说明](RULE-LAYOUT.md#作者提供语义不提供逐行坐标)。

## 组卷蓝图

```yaml
schema_version: 1
components_file: components.yaml
page:
  width: 595
  height: 842
  font_size: 11.3
  line_height: 24.05996
numbering: {mode: continuous, start: 1}
groups:
  - id: V2
    title: 問題１
    items: [V-07, V-08]
    options_columns: 2
    sidebar: {text: 語彙, position: left, y: 110, height: 95}
  - id: V1
    title: 問題２
```

| 字段 | 取值、默认与作用 |
| --- | --- |
| `groups` | 题组顺序；组内 `items` 省略取全组，只可选择直接条目 ID，不能越过篇章选关联题 |
| 组内 `title` | 覆盖显示标题 |
| `numbering.mode` | `continuous`、`source`、`per_group`；`numbering.start` 为全册起始题号，默认1 |
| 组内 `numbering`、`number_start` | 前者覆盖该组编号模式；`per_group` 使用组内 `number_start`，默认1 |
| `page.width`、`page.height` | 固定 A4 `595 × 842 bp`；页边距、版心、字号、行距可调 |
| `components_file` | 相对蓝图目录；内容如 `components: {reading: {options_columns: 1}}` |
| `group_defaults` | 共用设置；题型组件设置覆盖它，显式组配置优先 |
| `cover`、`header` | 封面、页眉配置；`cover: false` 省略封面和背页 |
| `sidebar` | `position: outer\|inner\|left\|right`；`false` 关闭分区标记 |
| `options_columns` | 仅 `auto`、1、2、4 |
| `table_column_widths`、`table_column_alignments` | 按列数配置列宽和对齐 |
| `table_font_size`、`table_line_height` | 表格字号、行距 |
| `table_cell_padding_x`、`table_cell_padding_top`、`table_cell_padding_bottom` | 表格内边距 |
| `new_page` | 题组级布尔值，默认 `true` 另起页；规则版 `false` 允许同科目接排 |
| `group_gap` | 同页组间距，默认当前 `line_height`；有限非负数，仍保留标题注音上伸所需距离，新页不加 |
| `body_start_adjust` | 标题后起排偏移；`new_page: false` 时须非负 |
| `start_on` | `left\|right`；同页请求检查当前页，必要时换页 |
| `page_number_start` | 默认1；插入空白页计入输出页序 |
| `items_per_page` | 听力每内容页题数，正整数，默认2；例题默认独立 |
| `full_page_items` | 听力选择题组中需要独页的大图题 ID 列表；只能引用本组非例题，不能重复。其前后均分页，其余题仍使用 `items_per_page` |
| `passages_new_page` | 是否每篇阅读另起页 |
| `questions_new_page` | 材料之后是否另起题页；完形默认 `true`。规则版完形或阅读材料已跨页时，题目从材料末页续排；单页材料仍按此设置换页 |
| `material_line_height` | 完形正文默认19.8bp；普通阅读沿用页面行距，不为长文压缩 |
| `material_intro_line_height`、`material_title_line_height`、`material_note_line_height` | 完形框外引导语默认页面行距、标题默认48.12bp；释义默认完形19.89bp、阅读24.06bp |
| `heading_layout` | 听力使用 `stacked` |
| `heading_size`、`instruction_font_size`、`instruction_line_height`、`instruction_width` | 标题与说明尺寸；说明宽度不可超过版心 |
| `layout: facing_pages` | 左页问题、右页参考材料；图片按长宽比排入 |
| `reference_font_size`、`reference_line_height`、`reference_outset` | 对页文字字号、行距、外扩量，分别默认9.2、13.68、16.95 |

同页题组示例（标准蓝图均保留 `new_page: true`）：

```yaml
groups:
  - id: V1
  - id: V2
    new_page: false
    group_gap: 24.06
```

同页排版保留标题和首个内容单元，放不下则换页；仅当整块连新页也放不下时，才允许可拆首项跨页。标题加不可拆首单元仍超页会报错。跨科目、对页和听力正式题分页约束优先。详见[同页规则](RULE-LAYOUT.md#同页连续题组)。

## 公共元数据

独立 YAML，顶层为 `schema_version: 1`、`schema_kind: exam_metadata`。

| 字段 | 内容 |
| --- | --- |
| `labels` | 题册、注意事项、填写栏、时长、页眉页脚等公共显示文字或格式 |
| `booklets.written`、`booklets.listening` | `title`、`subject_ja`、`subject_en`、`time_minutes`、`notices`，以及可选封面标识 `session_label`、`form_symbol` |
| `notices` 每项 | 日文 `text` 和可选英文 `english`；允许 `{body_pages}` |
| `sections.V/G/R/L.sidebar_label` | 科目侧边分区文字 |
| `assets` | `written_back`、`listening_back`、`reading_interleaf` 等独立素材引用；有 `reading_interleaf` 时，规则版跨页完形/阅读单元自动左页起排 |

范例：`content/common/metadata.yaml`。优先级为 `--metadata` > 当前题库 `metadata.yaml` > 公共文件，整份选择、不逐项合并。`{body_pages}` 取实际正文页数。

年份与圈标均可省略、设为 `null` 或空字符串；非空时只叠加在对应题册封面第一页，不移动原有元素：

```yaml
booklets:
  written:
    session_label: "（２０２３－２）"
    form_symbol: A
  listening:
    session_label: "（２０２３－２）"
    form_symbol: B
```

| 字段 | 限制与字体 |
| --- | --- |
| `session_label` | 最多16个无空白可打印字符，宽≤220bp；建议全角。Gothic MB101 Pro R + `FakeBold=1.5` |
| `form_symbol` | 一个大写 ASCII 字母；New Century Schoolbook Roman Regular，圆圈独立绘制 |

只需为非空字段配置字体；路径及 C059 自由替代见[字体说明](FONTS.md)。

## 生成模式与错误处理

所有命令从仓库根目录执行，安装见 [README](../README.md#生成第一份-pdf)。`python3 build.py --help` 查看当前参数；每次构建一套题库的一种题册。

| 参数 | 默认与注意事项 |
| --- | --- |
| `--paper NAME` | 默认 `paper-a`，读取 `content/NAME/`；NAME限英文字母、数字、下划线、连字符，不是目录路径 |
| `--booklet written/listening` | 默认 written；自动选择相应默认蓝图，不能选择另一册别的题组 |
| `--blueprint FILE` | 默认 `blueprints/<booklet>.yaml`；显式指定后不随booklet替换，2014笔试需 `blueprints/2014-12-written.yaml` |
| `--metadata FILE` | 按前述整份元数据优先级选择 |
| `--fonts FILE` | 默认根目录 `fonts.yaml`；推荐私人配置 `private/fonts.yaml`，对应路径规则见 [FONTS](FONTS.md) |
| `--output-dir DIR` | 输出根目录，默认 `output/rules`；不会再自动追加rules，相同题册重跑会覆盖其产物 |
| `--no-compile` | 完成排版、字形检查、TeX和报告生成，跳过PDF编译；仍需有效字体，且会改写中间产物 |
| `--rules` | 当前默认流程的可省略别名；旧 `--precise` / `--recompose` 不再支持 |

`--no-compile` 会清理工程内旧 `main.pdf`，但保留输出根目录已有的 `N1-<paper>-<booklet>.pdf`；失败的构建也可能留下旧报告。只有**本次命令成功、当前报告 `compiled: true`、实际PDF存在且页数一致**，才能确认本次编译完成；外观仍须另行检查。

未知材料、错误选项数量、缺字或不可容纳的单元会报错，不能通过删文字、随意换字族或裁切绕过。内容增减可能改变断行和页数；布局规则见 [RULE-LAYOUT](RULE-LAYOUT.md)，开发与回归见 [ARCHITECTURE](ARCHITECTURE.md)。

## 输出文件

成品为 `<输出根目录>/N1-<paper>-<booklet>.pdf`，工程为同目录的 `<paper>-<booklet>/`。构建不会覆盖 `examples/`。

| 工程文件 | 用途与边界 |
| --- | --- |
| `main.pdf`、`main.tex`、`content.generated.tex`、`pages/` | 实际编译产物及生成工程；TeX不是永久编辑入口 |
| `build-report.json` | compiled、正文页/总页数、组件参数和输入摘要；BUILT单独不代表PDF或视觉通过 |
| `selected-content.yaml` | 本次选题、顺序及重编号结果；编辑应回到content源文件 |
| `material-spreads.json` | 完整材料单元的印刷起止页和新增隔页；不是PDF物理页码 |
| `render-report.json` | 字体路由、封面字体名称、路径/摘要和警告；PASS不代表实际编译或外观正确 |
| `metadata-layout-report.json` | 固定元数据组件的文字布局 |
| `item-layout.json`、`semantic-ledger.json` | 题目布局和固定组件语义追踪；不能代替全文及图像核对 |
| `scene.json`、`resolved.json` | 场景命令、字形与素材绑定 |
| `composition-font-usage.json` | 包含测量用字，不能直接当成最终PDF的字体/字形使用清单 |
| `inputs/`、`assets/` | 输入和素材归档；inputs包含该题库所有YAML（也包括本册未使用者），配置/报告可能含私人路径 |

通常查看顶层成品PDF与必要报告即可；不要将整个工程目录打包给只需浏览PDF的使用者。详细验收与交付步骤见 [内容指南](CONTENT-GUIDE.md#4-检查并交付)。
