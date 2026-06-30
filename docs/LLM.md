# LLM 讲解增强

PaperScout 默认仍然可以不用 LLM 运行。`paperscout explain` 的基础模式会从论文和 SI 的解析文本里抽取证据片段，生成结构化 Markdown 报告。

如果需要更自然、更连贯的讲解，可以显式开启 LLM 模式：

```bash
paperscout explain \
  --materials data/cache/materials/parsed/<materials-id>.json \
  --requirements "Chemistry + AI; molecular dynamics; more math" \
  --llm
```

## SiliconFlow 配置

SiliconFlow 提供 OpenAI-compatible 的 chat completions API。当前实现使用：

```text
https://api.siliconflow.cn/v1/chat/completions
```

不要把 API key 写进命令行或提交到 Git。推荐在本地创建 `.env.local`：

```bash
cp .env.example .env.local
```

然后编辑 `.env.local`：

```text
SILICONFLOW_API_KEY=你的本地密钥
SILICONFLOW_MODEL=你想使用的模型名
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

`.env.local` 会被 `.gitignore` 忽略。模型名需要按 SiliconFlow 当前模型列表填写；不要假设某个模型永远存在或价格不变。

也可以临时在命令行指定模型名：

```bash
paperscout explain \
  --materials data/cache/materials/parsed/<materials-id>.json \
  --llm \
  --llm-model "Qwen/your-model-name"
```

API key 仍然应放在环境变量或 `.env.local`，不要通过命令行参数传入。

## 工作方式

LLM 模式不是直接把整篇 PDF 丢给模型。流程是：

1. Stage 6 把论文 PDF 和 SI 准备成结构化材料。
2. Stage 7 先生成证据抽取报告。
3. Stage 7.5 把证据摘要、材料状态和缺失证据交给 LLM。
4. LLM 根据这些证据生成更自然的中文报告。

这样做的目的是降低幻觉风险，并保留 no-LLM fallback。

## 重要限制

- LLM 输出仍然可能出错，不能视为已独立核查论文结论。
- 如果证据摘要中没有公式、baseline、指标或超参数，LLM 不应该补写。
- PDF 抽取可能丢失公式、表格、图片和排版；需要回到原文核查。
- 不同模型的上下文长度、价格和可用性会变化，使用前应查看平台页面。

## 调试

如果想检查发送给 LLM 的内容，可以保存 prompt：

```bash
paperscout explain \
  --materials data/cache/materials/parsed/<materials-id>.json \
  --llm \
  --save-llm-prompt data/cache/llm-prompt.json
```

这个 prompt 可能包含论文/SI 片段，不应该提交到 Git。
