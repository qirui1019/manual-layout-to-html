# manual-yaml-to-html

把 `input/` 文件夹中的产品说明书 layout YAML 批量转换成 HTML 对照页。每个 HTML 页面左侧显示 YAML 模块内容，右侧显示该模块对应的图片，适合浏览器预览和打印检查。

## 目录结构

```text
manual-yaml-to-html/
├─ input/
│  └─ SEESII_layout.yaml
├─ images/
│  ├─ default-placeholder.png
│  └─ SEESII_layout/
│     ├─ ch1/
│     │  ├─ ch_1.png
│     │  └─ ch_2.png
│     └─ ch2/
│        └─ ch_1.png
├─ output/
├─ templates/
│  └─ compare_template.html
├─ convert.py
├─ requirements.txt
└─ README.md
```

## YAML 与图片命名规则

`input/` 中每个 `.yaml` 或 `.yml` 文件会生成一个同名 HTML：

```text
input/SEESII_layout.yaml -> output/SEESII_layout.html
```

YAML 文件名去掉扩展名后作为图片主目录名：

```text
images/SEESII_layout/
```

## ch 编号规则

模块不按中文名称匹配图片，而是按 YAML 中模块出现顺序编号：

```text
第 1 个模块 -> images/SEESII_layout/ch1/
第 2 个模块 -> images/SEESII_layout/ch2/
第 3 个模块 -> images/SEESII_layout/ch3/
```

每个 `ch` 目录中的图片可以命名为：

```text
ch_1.png
ch_2.png
ch_10.png
```

支持扩展名：`.png`、`.jpg`、`.jpeg`、`.webp`、`.svg`。图片会按数字顺序排序，所以 `ch_10.png` 会排在 `ch_2.png` 后面。

## default-placeholder 规则

当某个模块没有对应图片、图片目录不存在、目录为空或图片不可读时，右侧会显示 `images/` 下的默认占位图。

占位图文件名固定为 `default-placeholder`，扩展名自动识别：

```text
default-placeholder.png
default-placeholder.jpg
default-placeholder.jpeg
default-placeholder.webp
default-placeholder.svg
```

如果没有可用的 `default-placeholder`，HTML 中会显示灰色占位框，文字为“暂无配图”。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方式

默认增量处理：

```bash
python convert.py
```

强制全部重新生成：

```bash
python convert.py --force
```

只处理指定 YAML：

```bash
python convert.py --file SEESII_layout
```

只处理新增 YAML：

```bash
python convert.py --new-only
```

只强制重新生成指定 YAML：

```bash
python convert.py --file SEESII_layout --force
```

## 增量处理逻辑

默认运行 `python convert.py` 时，只会处理以下情况：

- `output/` 中还没有对应 HTML；
- YAML 文件比对应 HTML 更新；
- 模板 `templates/compare_template.html` 比对应 HTML 更新；
- `default-placeholder` 比对应 HTML 更新；
- YAML 对应图片目录中有图片比对应 HTML 更新。

已经是最新的文件会跳过，并输出：

```text
SKIP: SEESII_layout.yaml is up to date
```
