# 内容编辑与编排示例

这份示例把第一套的部分题目改编成 4 页功能检查卷：交换 V2/V1 的顺序，筛选题目，加长含 ruby 的题干，等长替换另一题，并新增 V99 选择题组。来源题号统一改排为 1–8。

正文可编辑 `content/V.yaml`、`content/G.yaml`。`blueprint.yaml` 控制题组顺序、题目选择、两列选项、连续编号和侧栏。前三页使用全局 `sidebar.text: 編集確認`；第四页以分组 `sidebar.text: 文法検証` 覆盖。

在项目根目录运行：

```bash
cp -R examples/functional-check/content content/functional-check
python3 build.py --paper functional-check --booklet written --blueprint examples/functional-check/blueprint.yaml
```

如 `content/functional-check` 已存在，直接编辑或更新其内容文件，避免重复复制成嵌套目录。

也可运行自动验收工具；它会创建没有输入 PDF、没有预生成输出的临时项目，并使用另一个内容目录名称编译：

```bash
python3 tools/check_functional.py --output-dir output/functional-check-verification
```

此样例是功能演示，新增题目不包含标准答案。`content/R.yaml`、`content/L.yaml` 为复制的原始内容，本蓝图未选用。

带上封面并验证封面页数说明，可运行：

```bash
python3 tools/check_functional.py --output-dir output/functional-check-with-cover --with-cover
```

该示例生成 6 页 PDF（2 页封面、4 页正文），封面日英页数说明均为 4 页。
