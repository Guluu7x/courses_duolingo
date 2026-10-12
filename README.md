# 编程闯关

多邻国式的编程闯关课程网站。顶部可以切换课程，每门课程分别保存进度。

## 结构

```
index.html               生成的网站（不要手动改）
courses/catalog.json     课程列表：顺序、菜单里的短名、图标
courses/*.json           每门课程的题目
src/engine.html          网站引擎（课程切换、中文界面、主屏幕 App 设置）
tools/validate_course.py 课程格式检查
build_site.py            检查所有课程并生成 index.html
```

## 加一门新课程

1. 在 `courses/` 里新建一个 JSON 文件，格式和 `pandas-seaborn.json` 一样。
   课程的 `id` 一旦发布就不要改，进度是按它保存的。
2. 在 `courses/catalog.json` 里加一行，例如
   `{ "file": "list-comprehension.json", "short": "列表推导式", "icon": "🧩" }`
3. 运行 `python3 build_site.py`，没有 ERROR 就提交并推送。GitHub Pages 会自动更新。

## 题目可以带的资料（让每道题不用翻讲义也能做）

每个知识卡或题目都可以加这些字段：

| 字段 | 显示成 |
|---|---|
| `code` | 题目下方的 Python 代码框（带高亮，太长可以左右滑） |
| `output` | 代码框下方的“输出 OUTPUT”框 |
| `codeCaption` | 代码框标题，默认 PYTHON，例如写 `命令行 TERMINAL` |
| `terms` | 术语对照表，例如 `[["标量", "scalar"], ["向量", "vector"]]` |
| `ref` | ⓘ 按钮，点开是底部弹出的资料卡：`{"title": "...", "body": "...", "code": "...", "output": "..."}`，也可以是一个列表 |

答题时右上角的 📖 按钮会列出本关已经看过的知识卡。
写课程时的规则：中文术语第一次出现时在括号里写英文；题目里提到讲义的代码，要么用 `code` 直接放出来，要么用 `ref` 放进 ⓘ。

## 进度保存在哪里

进度存在打开网站的那个浏览器里（localStorage）。换设备、换浏览器，
或者从 iPhone 主屏幕图标打开时，进度都分别记录。
