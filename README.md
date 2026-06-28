# PaperScout

PaperScout 是一个计划中的个人研究辅助工具，用来推荐、分析和追踪高关注度的 AI / AI for Science 论文。

它的目标不是声称某篇论文是“全网最好的”或“客观最热的”，而是在可监控的数据源中，根据近期注意力信号给出可复现、可检查的推荐，并生成一份严谨的论文阅读讲解。用户读完后可以对论文价值和讲解质量打分，系统再根据历史反馈逐步调整推荐和讲解风格。

第一版计划做成命令行工具，不做完整网页应用。如果之后这个工具足够有用，再考虑加轻量网页界面，方便朋友使用。

## 早期范围

项目的早期版本只覆盖真正需要的每周读论文流程：

- 每次运行时询问本周的论文要求；
- 从监控来源或本地候选文件中推荐一篇未重复的论文；
- 说明为什么推荐这篇论文；
- 生成结构化的论文和 SI 阅读报告；
- 收集用户反馈；
- 保存本地历史记录。

早期版本不需要精美前端、登录系统、数据库或线上部署。

## 预期流程

1. 每次运行都询问读者对论文的要求。
   - 如果没有特殊要求，就记录为“无额外约束”。
   - 要求可以包括研究方向、方法类型、任务、模型类别、数学深度、实验类型或排除规则。

2. 收集 AI / AI4S 候选论文。
   - 注意力窗口设为最近 30 天。
   - 论文不一定必须是最近 30 天发表的。
   - 候选注意力信号可以包括近期引用、GitHub stars、代码仓库活跃度、Papers with Code 活动、报告或视频数量、博客或新闻可见度等。

3. 用透明的评分规则排序候选论文。
   - 每次推荐都要说明哪些信号贡献了分数。
   - 缺失或噪声较大的信号要明确标注。
   - 除非用户明确要求重读，否则排除已经推荐过的论文。

4. 获取并分析被选中的论文和 supplementary information。
   - 论文核心想法和动机
   - 数学定义和推导
   - 方法结构或算法流程
   - 实验设计和 baseline
   - 消融实验和失败模式
   - 可复现性信息
   - 局限性、假设和可能的过度声称

5. 收集读者反馈。
   - 论文有用程度评分
   - 讲解质量评分
   - 可选标签：哪些部分有用，哪些部分没用
   - 对后续推荐和讲解风格的备注

6. 保存历史记录。
   - 避免重复推荐。
   - 根据高评分论文调整后续推荐倾向。
   - 保留足够元数据，让未来的推荐可以被审计。

## 界面策略

PaperScout 应该先做命令行版本，因为这个项目的核心问题是推荐质量、论文分析质量和历史记录的可复现性。前端界面只有在基础流程已经可靠之后才值得做。

计划中的界面阶段：

1. 个人使用的命令行工具。
2. 可选的轻量本地网页界面，例如 Streamlit 或 Gradio。
3. 如果确实需要分享给更多人，再考虑多用户版本、账号、存储、认证、部署和费用控制。

如果未来给朋友使用，可以在进入工具时让用户选择初始兴趣方向。示例方向包括：

- CS-AI
- Math + AI
- Chemistry + AI4S
- Biology + AI4S
- Materials + AI
- Physics + AI
- General AI4S

兴趣方向应该可以编辑，并且应该支持自由文本备注，因为固定分类很难完整表达研究兴趣。

## 科学谨慎原则

注意力不等于质量。引用有滞后性，stars 可能反映宣传效果而不是科学价值，视频和社交媒体热度噪声很大，AI4S 论文还经常依赖细微的数据、单位、物理假设和评估协议。

因此，PaperScout 应该直接报告不确定性。如果元数据不完整、SI 找不到、PDF 解析失败，或者实验结论无法从论文材料中核查，报告里应该明确说明，而不是假装已经验证。

## 仓库结构

```text
PaperScout/
  README.md
  configs/                  运行配置和排序权重
  data/
    cache/                  API 或网页响应缓存
    history/                本地推荐历史和反馈历史
    processed/              标准化后的元数据和中间结果
    raw/                    原始元数据或源文件
  docs/
    decisions/              项目设计决策记录
  notebooks/                探索性分析，不放生产逻辑
  prompts/                  排序和论文讲解的提示词模板
  reports/                  生成的论文讲解报告
  scripts/                  小型命令行工具
  src/
    paperscout/
      analysis/             论文和 SI 分析流程
      collectors/           数据源适配器
      feedback/             评分和偏好更新
      interfaces/           CLI 或未来 UI 入口
      ranking/              注意力评分和候选排序
      recommender/          去重和个性化推荐逻辑
      storage/              本地持久化和数据结构
  tests/                    单元测试和集成测试
```

## 早期 MVP 范围

第一个可用版本应该尽量小：

1. 询问读者本次需求。
2. 加载或收集一个小规模候选论文集合。
3. 用简单、可解释的规则给候选论文排序。
4. 选择一篇未重复推荐的论文。
5. 根据论文和 SI 生成结构化讲解。
6. 本地保存推荐记录和反馈。

网页界面、自动长期趋势建模、多论文文献图谱等功能都应该等基础流程可靠之后再考虑。

## 命令行用法

当前早期版本支持从手动候选 JSON 文件中推荐一篇未重复论文：

```bash
paperscout recommend --candidates data/raw/candidates.example.json
```

如果不传 `--requirements`，命令会用分层菜单询问本次想看的论文方向。菜单会先询问大方向，再询问细分方向，然后询问讲解偏好和自由文本补充。

大方向不局限于传统 AI4S，也可以是更广泛的 AI 交叉方向，例如：

- CS-AI / machine learning methods
- Chemistry + AI
- Biology + AI
- Materials + AI
- Medicine / Health + AI
- Economics / Finance + AI
- Earth / Climate / Energy + AI

推荐结果会保存到 `data/history/recommendations.jsonl`，该文件默认不会被 Git 跟踪。

也可以先从真实元数据源收集候选论文，再推荐：

```bash
paperscout collect \
  --query "AI chemistry molecular dynamics" \
  --source arxiv \
  --output data/raw/candidates.generated.json

paperscout recommend --candidates data/raw/candidates.generated.json
```

当前 `collect` 默认只查询 arXiv。Semantic Scholar 和 GitHub 支持已经存在，但仍然建议谨慎使用：Semantic Scholar 引用数不是最近 30 天新增引用，GitHub repository 只有在候选论文元数据明确包含 repo URL 时才会附加到论文候选上；arXiv 摘要里明写的 GitHub 链接会被结构化保存，但不会做标题模糊匹配。

也可以显式传入本次需求和路径：

```bash
paperscout recommend \
  --candidates data/raw/candidates.example.json \
  --requirements "Chemistry + AI4S, more experiments" \
  --history data/history/recommendations.jsonl
```

## GitHub 策略

这个仓库可以较早推到 GitHub，但在此之前应先完成基本卫生检查：

- 不提交 API key；
- 不提交私人阅读历史；
- 不提交下载的论文 PDF 或 SI；
- 不提交私人生成报告；
- 明确 license 策略；
- 至少有一个可安装的 Python 项目骨架。

如果项目还处在实验阶段，可以先用 private repo。等 CLI MVP 能稳定工作、README 能准确说明项目限制后，再改成 public。

## 数据和隐私

`data/` 下的本地运行数据和 `reports/` 下的生成报告默认被 Git 忽略。这样可以避免把个人阅读历史、缓存文件和可能有版权问题的 PDF 提交到公开仓库。

如果之后需要公开示例数据，应使用小规模、合成的或明确允许再分发的数据。

## 当前状态

当前仓库已经有本地历史记录、手动候选论文加载、透明评分、去重推荐、命令行推荐入口，以及 arXiv / Semantic Scholar / GitHub 的早期元数据采集流程。真实数据源可以先导出为候选 JSON，再交给推荐命令使用。

仍未完成的核心部分包括：近期注意力信号的更严谨排序、论文 PDF 和 SI 的解析、结构化讲解生成、反馈收集入口，以及根据历史反馈调整推荐和讲解风格。
