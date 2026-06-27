# 手动候选论文格式

阶段 2 使用本地 JSON 文件输入候选论文。这个模式的目的不是自动发现论文，而是先验证排序、去重和历史记录是否可靠。

候选文件可以是一个对象，里面包含 `candidates` 列表：

```json
{
  "candidates": [
    {
      "paper": {
        "title": "Example AI4S Paper With Code",
        "authors": ["Example Author"],
        "year": 2026,
        "arxiv_id": "2601.00001",
        "url": "https://arxiv.org/abs/2601.00001"
      },
      "attention": {
        "recent_citation_count": 18,
        "github_stars": 120,
        "github_recent_commits": 8,
        "paper_with_code_has_entry": true,
        "video_or_talk_count": 2,
        "blog_or_news_count": 1,
        "source_confidence": 0.8
      },
      "requirement_match_score": 1.5,
      "notes": ["Fake example data."]
    }
  ]
}
```

也可以直接使用候选列表作为顶层 JSON。

## 字段说明

`paper` 是必需字段，使用阶段 1 中的论文元数据结构。至少需要 `title`，最好提供 DOI、arXiv ID、Semantic Scholar ID 或 URL 中的一个，这样后续可以可靠去重。

`attention` 是手动提供的注意力信号。当前默认支持：

- `recent_citation_count`
- `github_stars`
- `github_recent_commits`
- `paper_with_code_has_entry`
- `video_or_talk_count`
- `blog_or_news_count`
- `source_confidence`

`requirement_match_score` 是候选论文和本次需求的匹配程度。早期阶段先手动填写，后续 CLI 或 collector 可以再自动化。

## 评分说明

评分配置在 `configs/ranking.json` 中。

计数型信号不会直接使用原始数值，而是使用 `log1p(value)`。这样做是为了避免 GitHub stars 这类大数值直接压倒其他信号。

缺失的信号不会默默当作真实的 0，而是记录到 `missing_signals` 中，方便之后解释推荐结果。

## 当前限制

当前只支持 JSON，不支持 YAML。这个选择是刻意的：阶段 2 先避免引入额外依赖，把核心流程跑通。以后如果手写候选文件变得频繁，可以再加 YAML 支持。
