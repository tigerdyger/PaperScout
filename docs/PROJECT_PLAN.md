# PaperScout 项目计划

这个文档用于规划 PaperScout 的分阶段实现。

项目应该先做成个人每周读论文的工具，而不是一开始就追求“全网客观最热论文”。后者定义不清、难以复现，也容易带来不必要的 API 调用和模型费用。

第一阶段实现目标是命令行工具。前端、登录、部署和多用户功能都放到后面。

## 核心产品定义

PaperScout 每次运行推荐一篇 AI / AI for Science 论文，依据包括：

- 本次运行时读者给出的需求；
- 最近 30 天内可监控的数据源中的注意力信号；
- 本地历史记录，用来避免重复推荐；
- 过去反馈，用来逐步调整推荐方向和讲解风格；
- 如果未来分享给朋友使用，可以增加读者兴趣偏好档案。

关键表述：

> PaperScout 推荐的是“监控来源中的高关注论文”，不是“全网客观最高关注论文”。

## 不可妥协的原则

1. 每次运行都询问需求。
   - 如果用户没有特殊要求，就记录为 `no_extra_constraints`。
   - 不要静默假设用户一定偏好某个子领域。

2. 排序必须可审计。
   - 记录每个分数组件。
   - 明确记录缺失信号。
   - 在没有证据说明复杂模型有效之前，评分公式保持简单。

3. 控制成本。
   - 先做便宜的元数据筛选。
   - 只对最终选中的论文做深度分析。
   - 缓存 API 响应、PDF 解析结果和中间摘要。
   - 当不确定性很高时，优先让用户确认，不做大规模网页抓取。

4. 保持科学谨慎。
   - 注意力不是质量。
   - 明确标注不确定性。
   - 区分“论文声称”和“已经核查的事实”。
   - 主动指出不清楚的单位、数据集、假设、baseline 和评估指标。

5. 代码保持简单。
   - 先做命令行流程。
   - 先用本地文件，暂时不引入数据库。
   - 只有在重复代码已经明显造成负担时，才增加抽象。

6. 第一版不做多用户系统。
   - 个人每周使用不需要登录系统。
   - 如果之后给朋友用，先做轻量本地网页界面，再考虑线上服务。
   - 先把兴趣方向作为数据建模问题，而不是认证问题。

## MVP 范围

PaperScout 的 MVP 不是完整软件，而是一个可靠的每周读论文闭环：

- 询问本次论文需求；
- 推荐一篇未重复论文；
- 说明推荐所依据的注意力信号；
- 生成结构化阅读报告；
- 收集反馈；
- 本地保存历史。

MVP 不包括：

- 前端；
- 账号登录；
- 云端部署；
- 生产数据库；
- 全网自动趋势追踪；
- 复杂个性化推荐模型。

## 阶段 0：仓库基础和关键决策

目标：让仓库适合后续开发，也适合将来公开。

任务：

- 添加最小 Python 项目配置。
- 决定支持的 Python 版本。
- 如果准备公开仓库，添加 `LICENSE`。
- 添加 `.env.example`，说明可选 API key。
- 添加简短说明，提醒不要提交本地历史、PDF 和生成报告。

产物：

- `pyproject.toml`
- `.env.example`
- 可选的 `LICENSE`
- 可选的 `docs/decisions/0001-initial-scope.md`

需要用户确认：

- 使用 MIT License，还是暂时不加 license？
- 生成报告是否默认只保存在本地？是否允许以后提交精选示例报告？
- GitHub 仓库先 private，等 CLI MVP 稳定后再 public，还是阶段 0 完成后就 public？

完成标准：

- 新 clone 的仓库可以用 editable mode 安装。
- Git 会忽略 secrets、PDF、缓存数据和个人历史。

## 阶段 1：本地数据模型和历史记录

目标：先定义 PaperScout 需要记住什么，再写采集逻辑。

任务：

- 定义论文元数据结构。
- 定义推荐历史结构。
- 定义反馈结构。
- 定义轻量读者偏好档案结构。
- 先用 JSONL 保存本地记录。
- 实现简单的读写工具。

建议文件：

- `src/paperscout/storage/schemas.py`
- `src/paperscout/storage/jsonl_store.py`
- `data/history/recommendations.jsonl`
- `data/history/feedback.jsonl`
- `data/history/profile.json`

最小字段：

- 论文 ID：DOI、arXiv ID、Semantic Scholar ID，或者 fallback URL。
- 标题、作者、venue/source、年份。
- 论文 URL 和 PDF URL。
- SI URL 或本地路径。
- 推荐时间。
- 本次用户需求。
- 分数拆解。
- 讲解报告路径。
- 用户反馈评分和备注。

初始偏好档案字段：

- `preferred_fields`：例如 `CS-AI`、`Math + AI`、`Chemistry + AI4S`、`Biology + AI4S`、`Materials + AI`、`Physics + AI`、`General AI4S`。
- `free_text_preference`：例如“更希望看有数学推导和认真实验设计的论文”。
- `explanation_style`：例如 `balanced`、`more_math`、`more_experiments`、`more_reproducibility`。

完成标准：

- 测试可以写入一条推荐记录并读回。
- 至少能根据 arXiv ID、DOI 和 canonical URL 做重复检测。
- 本地偏好档案可以保存和读取，但每次运行不强制必须有偏好档案。

## 阶段 2：手动候选论文模式

目标：先验证推荐、排序、去重和历史记录，不依赖外部 API。

原因：

项目应该先证明核心流程能跑通，再加入数据源。这样可以避免在推荐逻辑还没成型时，就把时间花在外部 API、限流和数据清洗上。

任务：

- 设计一个小型候选论文输入格式。
- 支持从本地 JSON 或 YAML 文件读取候选论文。
- 用手动提供的注意力字段给候选论文排序。

建议文件：

- `configs/ranking.yaml`
- `src/paperscout/collectors/manual.py`
- `src/paperscout/ranking/scorer.py`
- `tests/test_ranking.py`

示例注意力字段：

- `recent_citation_count`
- `github_stars`
- `github_recent_commits`
- `paper_with_code_has_entry`
- `video_or_talk_count`
- `blog_or_news_count`
- `source_confidence`

完成标准：

- 给定 5 篇 mock 候选论文和 1 条重复历史记录，程序能选出最高分且未重复的论文。
- 输出中包含分数拆解，而不只是最终分数。

## 阶段 3：CLI MVP

目标：做出第一个可用的命令行流程。

任务：

- 添加 CLI 命令。
- 运行时询问用户需求。
- 可选读取本地偏好档案。
- 从手动候选模式加载候选论文。
- 排除已经推荐过的论文。
- 推荐一篇论文。
- 保存推荐记录。

建议命令：

```bash
paperscout recommend --candidates data/raw/candidates.example.json
```

建议文件：

- `src/paperscout/interfaces/cli.py`
- `src/paperscout/recommender/select.py`
- `tests/test_recommender.py`

完成标准：

- CLI 会询问本次需求。
- 如果本地偏好档案存在，CLI 可以读取并使用。
- CLI 输出推荐论文和分数拆解。
- CLI 会把推荐记录保存到本地。

## 阶段 4：真实元数据采集

目标：从少数可靠来源收集候选论文元数据。

初始数据源优先级：

1. arXiv：论文元数据。
2. Semantic Scholar：引用和论文元数据。
3. GitHub：如果能找到代码仓库，则记录仓库注意力信号。

早期避免：

- 大范围社交媒体抓取。
- 非官方 Google Scholar 抓取。
- 对每个候选论文都做昂贵的全网搜索。
- 完全自动统计视频和博客数量。

任务：

- 添加各数据源 collector。
- 缓存原始 API 响应。
- 标准化不同来源的数据结构。
- 添加限流和重试。
- 记录 source confidence。

建议文件：

- `src/paperscout/collectors/arxiv.py`
- `src/paperscout/collectors/semantic_scholar.py`
- `src/paperscout/collectors/github.py`
- `src/paperscout/collectors/cache.py`

完成标准：

- 一次运行可以从监控来源获取有界候选集合。
- 相同查询再次运行时默认使用缓存，除非用户要求刷新。
- 缺少 API key 时给出清楚错误信息，而不是直接抛出难读的 stack trace。

## 阶段 5：注意力排序初版

目标：用有文档说明的简单公式替代临时排序。

任务：

- 定义归一化分数组件。
- 近期注意力权重要高于历史总注意力。
- 谨慎处理缺失信号和低置信度信号。
- 保存分数解释。

建议公式：

```text
final_score =
  requirement_match_score
  + recent_attention_score
  + reproducibility_signal_score
  + source_confidence_score
  - duplicate_or_near_duplicate_penalty
```

注意：

不要太早过拟合评分公式。评分规则应该能用一段话解释清楚。

完成标准：

- 排序结果包含每个分数组件。
- 修改配置权重后，排序结果按预期变化。
- 测试覆盖缺失信号和重复论文排除。

## 阶段 6：论文和 SI 读取

目标：准备论文分析所需材料。

任务：

- 下载或接收本地论文 PDF。
- 下载或接收本地 SI 文件。
- 从 PDF 提取文本。
- 将论文和 SI 切分成章节。
- 把解析后的文本保存到缓存。
- 记录解析失败原因。

建议文件：

- `src/paperscout/analysis/materials.py`
- `src/paperscout/analysis/pdf_extract.py`
- `tests/test_materials.py`

需要处理的失败模式：

- PDF 文本提取乱码。
- SI 不可用。
- SI 是 zip 文件，或者包含非 PDF 文件。
- 论文太长，不能一次放入模型上下文。
- 图、公式和表格可能无法被普通文本提取准确保留。

完成标准：

- pipeline 可以读取一篇论文 PDF 和可选 SI。
- 输出明确说明哪些内容成功提取，哪些没有成功提取。

## 阶段 7：结构化论文讲解

目标：生成每周阅读报告。

报告章节：

- 为什么推荐这篇论文。
- 一段话总结。
- 问题设定。
- 核心想法。
- 方法或算法。
- 数学定义和推导。
- 实验设计。
- baseline 和消融实验。
- 主要结果。
- 局限性和可能的过度声称。
- 可复现性检查。
- 建议阅读顺序。
- 阅读时应该思考的问题。

任务：

- 添加 prompt 模板。
- 分章节生成摘要和讲解。
- 对数学、方法和实验部分使用更强的分析流程。
- 将最终报告保存为 Markdown。

建议文件：

- `prompts/explain_paper.md`
- `prompts/check_claims.md`
- `src/paperscout/analysis/explainer.py`
- `reports/YYYY-MM-DD-paper-slug.md`

完成标准：

- 一篇选中论文可以生成可读的 Markdown 报告。
- 报告明确标注不确定性和缺失证据。
- 报告不会把论文作者的声称伪装成已经核查的事实。

## 阶段 8：反馈循环

目标：让评分影响后续行为，但不假装已经有大型推荐系统。

任务：

- 询问论文有用程度评分。
- 询问讲解质量评分。
- 询问可选标签或备注。
- 保存反馈。
- 计算轻量偏好提示。

初始反馈字段：

- `paper_usefulness`：1 到 5
- `explanation_quality`：1 到 5
- `too_basic`：true/false
- `too_advanced`：true/false
- `wanted_more_math`：true/false
- `wanted_more_experiments`：true/false
- `wanted_more_code_reproducibility`：true/false
- 自由文本备注

完成标准：

- 反馈会保存到本地。
- 未来运行时可以读取反馈，并打印偏好提示。
- 暂时不引入复杂个性化模型。

## 阶段 9：每周端到端流程

目标：让整个工具真正可以每周使用一次。

预期命令：

```bash
paperscout weekly
```

预期行为：

1. 询问本周需求。
2. 如果本地偏好档案存在，读取偏好。
3. 获取或加载候选论文。
4. 给候选论文排序。
5. 展示前几名候选论文和分数拆解。
6. 推荐一篇论文。
7. 深度分析前询问用户确认。
8. 分析论文和 SI。
9. 保存报告。
10. 询问反馈。
11. 保存历史。

完成标准：

- 一次运行不需要手动改文件就能完成。
- 第二次运行不会推荐同一篇论文。
- 深度分析前能显示或估算本次模型/API 成本。

## 阶段 10：公开 GitHub 前清理

目标：让仓库安全、清楚，适合公开。

这个阶段可以在 private repo 中较早完成，但必须在公开仓库前完成。

任务：

- 添加安装说明。
- 添加使用 fake 或可再分发数据的示例候选文件。
- 添加不包含受版权保护论文正文的示例输出。
- 如有必要，添加 CI 测试。
- 明确提醒：排序只基于监控来源中的信号。

完成标准：

- 公开读者不需要看到你的私人数据，也能理解项目用途。
- 没有个人历史、API key、PDF 或私人生成报告被 Git 跟踪。

## 阶段 11：可选的朋友友好界面

目标：让少数朋友可以使用 PaperScout，但不把项目过早变成生产级 Web 服务。

推荐的第一步：

- 用 Streamlit 或 Gradio 做轻量本地网页界面。
- 让用户开始时选择兴趣方向。
- 让用户补充自由文本偏好。
- 默认仍然本地保存数据，除非有明确理由部署。

可能的 onboarding 字段：

- 兴趣方向：`CS-AI`、`Math + AI`、`Chemistry + AI4S`、`Biology + AI4S`、`Materials + AI`、`Physics + AI`、`General AI4S`。
- 阅读目标：快速了解、深入数学、实验设计、可复现性或代码实现。
- 讲解语言：中文、英文或双语。

这个阶段避免：

- 完整账号登录。
- 共享云端数据库。
- 公开部署。
- 自动计费或额度管理。

完成标准：

- 朋友可以在本地运行工具，并通过界面选择偏好，不需要手动改配置文件。
- CLI 和 UI 复用同一套后端逻辑。
- 默认不上传私人用户数据。

## 后续可选功能

这些功能应该等每周使用流程可靠之后再考虑：

- 生产级 Web 应用。
- 自动定时每周运行。
- 更多数据源。
- 更好的论文-代码仓库匹配。
- 图表和表格提取。
- 对历史报告做本地 embedding 检索。
- 主题聚类。
- 多论文比较报告。
- 导出到 Notion、Obsidian 或 Google Docs。

## 建议的下一步

先做阶段 0，然后做阶段 1。

第一个编码任务应该很小：

> 添加 Python 项目配置、最小 package 骨架，以及本地 JSONL 历史记录 schema。

在开始之前，需要先确认：

1. 是否使用 MIT License。
2. 生成报告是否默认只保存在本地。
3. 第一版界面和报告用中文、英文还是双语。
4. GitHub 是先 private，还是阶段 0 后直接 public。
