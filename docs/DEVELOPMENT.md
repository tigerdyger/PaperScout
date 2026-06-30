# 开发说明

这个仓库目前处在早期 CLI 阶段。已经具备本地历史记录、手动候选推荐、真实元数据采集、候选导出、论文 PDF/SI 材料准备和结构化 Markdown 报告生成功能，但还没有反馈入口、前端、登录或部署。

## 本地安装

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 本地检查

可以用下面的命令运行测试：

```bash
pytest
```

## 本地运行

安装后可以运行：

```bash
paperscout recommend --candidates data/raw/candidates.example.json
```

这会从手动候选文件中选择一篇未重复论文，并把推荐记录写入 `data/history/recommendations.jsonl`。如果不传 `--requirements`，CLI 会用分层菜单询问方向、细分方向和讲解偏好；如果要做脚本化测试，可以直接传 `--requirements`。历史文件默认被 Git 忽略。

也可以先收集真实元数据，再推荐：

```bash
paperscout collect \
  --query "all:molecular AND all:learning" \
  --source arxiv \
  --max-results 1 \
  --output data/raw/candidates.generated.json

paperscout recommend --candidates data/raw/candidates.generated.json
```

准备论文材料：

```bash
paperscout prepare-materials \
  --title "Example Paper" \
  --pdf /path/to/paper.pdf \
  --si /path/to/supporting_information.pdf
```

根据材料 JSON 生成结构化阅读报告：

```bash
paperscout explain \
  --materials data/cache/materials/parsed/<materials-id>.json \
  --requirements "Chemistry + AI; more math" \
  --output reports/example-paper.md
```

当前报告生成不需要 API key。它只做证据抽取和结构化整理，不会把未解析到的公式、表格或 SI 内容补写成确定结论。

如果要测试 SiliconFlow 等 OpenAI-compatible LLM 增强模式，先在本地 `.env.local` 中配置：

```text
SILICONFLOW_API_KEY=...
SILICONFLOW_MODEL=...
```

然后运行：

```bash
paperscout explain \
  --materials data/cache/materials/parsed/<materials-id>.json \
  --llm
```

不要把 `.env.local`、LLM prompt 缓存或生成报告提交到 Git。

记录阅读反馈：

```bash
paperscout feedback \
  --paper-usefulness 5 \
  --explanation-quality 4 \
  --wanted-more-math \
  --note "希望多讲公式假设"
```

如果不传分数和标签，CLI 会交互式询问。反馈会写入 `data/history/feedback.jsonl`，并更新 `data/history/profile.json`。

## 不要提交的内容

这些内容默认应该只保存在本地：

- `.env` 或任何包含 API key 的文件；
- 下载的论文 PDF、SI 或压缩包；
- `data/` 下的缓存、历史记录和中间数据；
- `reports/` 下的私人生成报告；
- 任何包含个人阅读偏好或评分历史的文件。

如果以后需要提交示例数据，应使用 fake 数据、合成数据，或明确允许再分发的数据。
