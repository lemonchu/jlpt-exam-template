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
- `｜商品《しょう|ひん》`：逐字注音；片段数量须等于汉字数，每段非空。不加分隔符则按整词处理，不自动猜读音。
- `__下線__`：下划线；允许 `__｜漢字《かんじ》__`。
- `**太字**`：粗体。
- `（　　　）`：全角填空括号；`__　　　__`：三字空线；`__★__`：同宽星号空线。
- `{{注1|用語}}`：行下小注；可写 `{{注1|｜漢字《かんじ》}}`。数字圆圈下标可写 `{{①|__語句__}}`。
- LF 表示明确分段；连续段落不保留原 PDF 任意行末换行。

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
| `table` | `rows` 为二维字符串列表，每行列数相同；`header_rows` 为表头行数，默认 0；可用 `borders: false` 隐藏单元格线，以 `width` 和 `align: left\|center\|right` 控制表格宽度与对齐；`column_alignments` 可逐列设置对齐，表头另可用 `header_bold`、`header_fill`、`header_alignments` |
| `image` | `asset` 为 `assets/` 下的相对文件路径；`alt` 为说明或转录，不打印 |
| `memo` | 可选 `label`，默认 `－メモ－`；可选 `height` 为该空白书写区固有高度，单位 bp |
| `separator` | 两部分材料之间的空白间隔 |

图像支持 PDF（第一页）、PNG、JPEG，适合广告或手写材料，不应代替可编辑题干与选项。`alt` 不修改图中文字。

表格列宽、纵排列高、图片位置优先放蓝图。复合听力中未指定 `style` 的段落按作答说明的字号、行距和粗体排版。

`rule_style` 标记引文、对话、通知、图注或参考资料等材料角色，只影响规则版。角色列表、嵌套限制与示例见[排版说明](RULE-LAYOUT.md#作者提供语义不提供逐行坐标)。

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
| `numbering.mode` | `continuous`、`source`、`per_group` |
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
| `passages_new_page` | 是否每篇阅读另起页 |
| `questions_new_page` | 材料之后是否另起题页；完形默认 `true` |
| `material_line_height` | 文章行距；G7默认19.8，正式选择题仍为24.05996 |
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

同页排版保留标题和首个内容单元，放不下则换页；仅当整块连新页也放不下时，才允许可拆首项跨页。标题加不可拆首单元仍超页会报错。跨科目、对页和听力正式题分页约束优先；旧 `--precise`、`--recompose` 在已有内容页上接排会报错。详见[同页规则](RULE-LAYOUT.md#同页连续题组)。

## 公共元数据

独立 YAML，顶层为 `schema_version: 1`、`schema_kind: exam_metadata`。

| 字段 | 内容 |
| --- | --- |
| `labels` | 题册、注意事项、填写栏、时长、页眉页脚等公共显示文字或格式 |
| `booklets.written`、`booklets.listening` | `title`、`subject_ja`、`subject_en`、`time_minutes`、`notices`，以及可选封面标识 `session_label`、`form_symbol` |
| `notices` 每项 | 日文 `text` 和可选英文 `english`；允许 `{body_pages}` |
| `sections.V/G/R/L.sidebar_label` | 科目侧边分区文字 |
| `assets` | `written_back`、`listening_back`、`reading_interleaf` 等独立素材引用 |

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

模式参数与默认目录见 [README](../README.md#排版模式)。`--output-dir` 覆盖输出根目录；其中 `N1-<题库>-<题册>.pdf` 为成品，`<题库>-<题册>/` 为工程与报告。旧产物不自动迁移，`examples/` 不自动覆盖。模式边界见[排版说明](RULE-LAYOUT.md)，维护检查见[架构说明](ARCHITECTURE.md)。

未知材料、选项数量错误、不可拆单元超限或缺字会报错。文字始终来自当前 YAML；内容增减可能改变断行和页数，任何模式都不保证任意新题逐像素复现原稿。

根目录 `fonts.yaml` 自动加载，也可用 `--fonts other-fonts.yaml` 指定配置；路径相对项目根目录或为绝对路径。`faces` 配置对应完整 OTF/TTF，`fonts.cover_session`、`fonts.cover_symbol` 配置可选封面字体。**默认 A/B 也可能需要完整字体**，例如 A 的「謎」需要 Ryumin。项目不跨原字族补字、不使用通用替代字体，详见[FONTS.md](FONTS.md)。
