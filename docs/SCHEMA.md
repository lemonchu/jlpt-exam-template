# 内容与配置格式，版本 1

这是现有引擎的编辑约定。内容、蓝图、公共元数据分别保存；题目内容中不写字体编号、逐字坐标、页边距、输出页码或强制分页。数值尺寸由蓝图控制，备忘空白区的固有高度是例外。

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

- `｜漢字《かんじ》`：注音，正文与注音分别保存语义角色。
- `__下線__`：下划线；允许 `__｜漢字《かんじ》__`。
- `**太字**`：粗体。
- `（　　　）`：全角填空括号；`__　　　__`：三字空线；`__★__`：同宽星号空线。
- `{{注1|用語}}`：行下小注；可写 `{{注1|｜漢字《かんじ》}}`。数字圆圈下标可写 `{{①|__語句__}}`。
- LF 表示明确分段；连续段落不保留原 PDF 任意行末换行。

使用原语言和实际标点，不根据题意修正错误选项或推断答案。YAML 中以特殊符号开头的字符串应加引号。

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

篇章含 `id`、`stimulus`、`questions`，可另有 `label`、`source_pages`。`questions` 中每项使用四选一结构。仅有印刷说明或备忘区时可写 `questions: []`，不据此推断音频题数。

完形的 `〔数字〕`、`〔数字-字母〕` 是题号引用，例如 `〔41〕`、`〔43-a〕`、`〔43-b〕`；字母后缀为一个 ASCII 字母。对应问题的 `source_number` 保存同一个数字。重排编号时同步替换引用数字，保留后缀。选项里的 a/b 仍按原文保存，普通年份不作为题号更新。

## 材料块

| `type` | 内容字段与含义 |
| --- | --- |
| `paragraph` | `text`；可选 `style: bold\|small`、`align: left\|center\|right`、非负数 `indent` |
| `heading` | `text`，作为材料标题 |
| `vertical` | `text`，按语义阅读顺序填写的纵排文章 |
| `box` | `blocks`，框内递归材料列表 |
| `table` | `rows` 为二维字符串列表，每行列数相同；`header_rows` 为表头行数，默认 0；可用 `borders: false` 隐藏单元格线，以 `width` 和 `align: left\|center\|right` 控制表格宽度与对齐；`column_alignments` 可逐列设置对齐，表头另可用 `header_bold`、`header_fill`、`header_alignments` |
| `image` | `asset` 为 `assets/` 下的相对文件路径；`alt` 为说明或转录，不打印 |
| `memo` | 可选 `label`，默认 `－メモ－`；可选 `height` 为该空白书写区固有高度，单位 bp |
| `separator` | 两部分材料之间的空白间隔 |

图像支持 PDF、PNG、JPEG；PDF 使用第一页。题干和选项不应以整页图片替代。独立广告和手写材料可以保留为图像；`alt` 的编辑不会修改图中的文字。

表格列宽、纵排列高、图片排入位置等优先放在蓝图，而非内容字段。复合听力中未指定 `style` 的 `paragraph` 默认按作答说明的字号、行距和粗体排版。

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

`groups` 决定采用顺序；`items` 省略表示全组，指定时只接受该组直接条目的 ID，关联追问不能越过篇章单独选入。`title` 可覆盖题组显示标题。编号模式为 `continuous`、`source`、`per_group`。

当前校准渲染器固定使用 A4 的 `595 × 842 bp` 页面；`page.width` 和 `page.height` 用于明确该约束，不能改成其他纸张尺寸。页边距、版心、字号和行距仍可由蓝图调整。

`components_file` 相对于蓝图目录，内容形如 `components: {reading: {options_columns: 1}}`；`group_defaults` 提供共用设置，显式组配置优先。相关题组的布局参数变化后，该题组重新排版；仅改变题组顺序时，可移动原组件并重新绘制页边装饰。

其他常用字段包括 `cover`、`header`、`sidebar`、`table_column_widths` 和 `layout: facing_pages`，可参考仓库内的现有蓝图。侧边分区位置支持 `outer|inner|left|right`；`sidebar: false` 关闭。单个选项列数只支持 `auto`、1、2、4。表格还可由蓝图统一设置 `table_font_size`、`table_line_height`、`table_cell_padding_x`、`table_cell_padding_top`、`table_cell_padding_bottom` 和按列数映射的 `table_column_alignments`。

`start_on: left|right` 指定题组的起始页奇偶性；插入的空白页计入封面页数。`page_number_start` 默认为1。`cover: false` 可省略封面和背页。

听力 `items_per_page` 默认为2，正整数表示一个内容页的题数；例题默认独立。阅读 `passages_new_page` 控制是否每篇另起。完形默认 `questions_new_page: true`，材料页后另起题页。`material_line_height` 可单独设置文章行距，G7默认19.8，正式选择题仍用24.05996。

听力标题使用 `heading_layout: stacked`；`heading_size`、`instruction_font_size`、`instruction_line_height` 和不超过版心的 `instruction_width` 可调整标题与说明。修改这些值会停用该标题的精确位置并按新参数重排。

`layout: facing_pages` 保持左页问题、右页参考材料。文字材料用 `reference_font_size`（默认9.2）、`reference_line_height`（默认13.68）和 `reference_outset`（默认16.95）控制；现有同结构的参考页可以复用实测位置，外部图像按长宽比排入。

## 公共元数据

元数据也是 YAML，顶层为 `schema_version: 1`、`schema_kind: exam_metadata`，与试题文件分开。

| 字段 | 内容 |
| --- | --- |
| `labels` | 题册、注意事项、填写栏、时长、页眉页脚等公共显示文字或格式 |
| `booklets.written`、`booklets.listening` | `title`、`subject_ja`、`subject_en`、`time_minutes`、`notices`，以及可选封面标识 `session_label`、`form_symbol` |
| `notices` 每项 | 日文 `text` 和可选英文 `english`；允许 `{body_pages}` |
| `sections.V/G/R/L.sidebar_label` | 科目侧边分区文字 |
| `assets` | `written_back`、`listening_back`、`reading_interleaf` 等独立素材引用 |

完整范例为 `content/common/metadata.yaml`。选择顺序是命令行 `--metadata`、当前题库的 `metadata.yaml`、公共文件；整份选择，不逐项合并。`{body_pages}` 由构建时的实际正文页数计算。

`session_label` 和 `form_symbol` 都可以省略、设为 `null` 或空字符串，此时封面不增加任何命令。需要时按题册分别填写：

```yaml
booklets:
  written:
    session_label: "（２０２３－２）"
    form_symbol: A
  listening:
    session_label: "（２０２３－２）"
    form_symbol: B
```

`session_label` 接受最多 16 个无空白的可打印字符，并且排版宽度不得超过 220bp；正式年份建议使用全角形式，如 `（２０２３－２）`。`form_symbol` 仅接受单个大写 ASCII 字母。两者只叠加在该题册封面第一页，不移动原有元素。年份使用 Gothic MB101 Pro R 并施加模板规定的粗体效果；圆内字母使用 New Century Schoolbook Roman Regular，外圈是独立矢量图形。两款字体均只在相应字段非空时需要，配置方法及 C059 自由替代见 [FONTS.md](FONTS.md)。

## 实测容量与错误处理

内容格式同时服务精确组件和规则排版。默认构建会自动判断：页面和蓝图保持兼容，且题组的字段结构、字符容量、空白、注音、行内标记及 `style`、`align`、`indent`、表格、图片等布局属性都符合校准契约时，使用精确位置；否则仅将不兼容的题组交给规则排版。当前 YAML 的每个字都会重新解析，模板内没有旧题文字作为兜底。

`--recompose` 会关闭题组、标题和例题的实测位置复用，用同一套字体与规则重新流排整卷。它用于验证自定义题、自动断行和分页，并不承诺复刻参考 PDF 的每个坐标；例如官方解答示例中的专用框格节奏会由通用块规则近似。通常无需手动选择“精确模式”：默认构建已经在安全兼容时自动使用，在内容或布局改变时自动退回规则。

未知材料类型、四选一数量错误、不可分割材料过大或最终缺字会明确报错。题干增减可能改变断行和页数；有限纸面不能在容纳任意内容的同时固定所有旧坐标。

项目 `fonts.yaml` 默认自动加载：`faces` 将五个正文原字体名称映射到本地完整 OTF/TTF，`fonts.cover_session` 与 `fonts.cover_symbol` 配置可选封面字体；原稿已有字形和同名字体的其他科目子集优先。可用 `--fonts other-fonts.yaml` 指定另一份本地路径配置。所有路径相对于项目根目录，也支持绝对路径。

仓库附有现有 A/B 内容所需的字体子集。自编内容出现未收录字符时，按 [FONTS.md](FONTS.md) 配置对应的完整字体。该版本不跨原字体补字，也不启用通用替代字体；缺少文件或所需字形时明确报错。编辑内容不需要在 YAML 中写字体编号或逐字坐标。
