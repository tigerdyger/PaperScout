# 论文和 SI 材料准备

阶段 6 的目标是把论文 PDF 和可选 supplementary information 准备成后续讲解阶段可以使用的文本材料。

当前实现遵循几个保守原则：

- 正文和 SI 都是证据来源；如果关键方法、实验或超参数只在 SI 中出现，后续分析不应该忽略。
- 本地只缓存解析结果和下载到缓存目录的原始材料，不把 PDF、SI 或私人材料提交到 Git。
- PDF 文本抽取不等于完整阅读。公式、表格、图和版式可能丢失，pipeline 会记录 warning。
- 缺失、无法下载、无法解析、过长和不支持的 SI 类型都要记录原因，而不是静默跳过。

## 命令行用法

本地 PDF：

```bash
paperscout prepare-materials \
  --title "Example Paper" \
  --pdf /path/to/paper.pdf
```

本地 PDF 加 SI：

```bash
paperscout prepare-materials \
  --title "Example Paper" \
  --pdf /path/to/paper.pdf \
  --si /path/to/supporting_information.pdf
```

URL 也可以作为输入。远程材料会下载到 `data/cache/materials/raw/`，解析结果会写入 `data/cache/materials/parsed/`。

```bash
paperscout prepare-materials \
  --title "Example Paper" \
  --pdf https://arxiv.org/pdf/2401.00001 \
  --cache-dir data/cache/materials
```

## 输出内容

`prepare_materials` 会生成：

- `documents`：每个材料的状态、文件类型、来源、章节、字符数和问题列表。
- `chunks`：按章节切分后的文本块，供后续报告生成或 evidence selection 使用。
- `issues`：汇总的解析问题，例如 PDF 版式损失、文本过短、文本疑似乱码、SI 缺失、zip 暂不支持、材料太长已切块等。

## 当前支持

- PDF：使用 `pypdf` 抽取文本。
- `.txt` / `.md`：直接作为文本材料读取。
- `.zip` / `.tar` / `.gz` / `.tgz`：记录为不支持的 archive，暂不自动解包。

## 当前限制

- 还不会自动发现出版社 SI 链接。
- 还不会解析 docx、xlsx、csv、html SI。
- 还不会从 PDF 中可靠保留公式、表格和图片。
- 章节识别是启发式的，主要识别 Abstract、Methods、Results、Discussion、Appendix 等常见标题。
- 后续可以用 `paperscout explain --materials <materials-json>` 基于解析结果生成结构化 Markdown 报告。
- 当前讲解阶段不调用 LLM，而是先做证据抽取和缺失证据标注。
