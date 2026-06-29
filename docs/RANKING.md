# 注意力排序公式

阶段 5 使用一个分组、可审计的简单公式。它不是质量评价，只表示在当前监控来源里观察到的注意力证据。

```text
final_score =
  requirement_match_score
  + recent_attention_score
  + reproducibility_signal_score
  + lifetime_attention_score
  + source_confidence_score
  - low_confidence_penalty
```

默认权重配置在 `configs/ranking.json` 中。

## 分数组件

`requirement_match_score` 直接来自候选论文和本次需求的匹配分。早期阶段它可以手动提供；后续会再做自动匹配。

`recent_attention_score` 表示近期注意力证据，默认包含：

- `recent_citation_count`
- `github_recent_commits`
- `video_or_talk_count`
- `blog_or_news_count`

`reproducibility_signal_score` 表示可复现性和代码可见度证据，默认包含：

- `paper_with_code_has_entry`
- `github_repository_present`

`lifetime_attention_score` 表示长期总注意力证据，默认包含：

- `github_stars`
- `github_forks`
- `semantic_scholar_citation_count`
- `semantic_scholar_influential_citation_count`

`source_confidence_score` 来自 `source_confidence`，用于表达这个候选记录来源是否可靠。

`low_confidence_penalty` 会在 `source_confidence` 低于阈值时扣分。默认阈值是 `0.5`。

## 归一化规则

计数型信号先做：

```text
normalized = min(1, log1p(value) / log1p(reference_value))
```

这样做的原因是 GitHub stars、引用数这类信号分布很偏，不能让一个特别大的历史总量直接压倒其他证据。

布尔型信号转为 `0` 或 `1`。`source_confidence` 这类有界信号会被限制在 `[0, 1]`。

每个信号组内部先按组内权重求归一化加权平均，再乘以组权重。默认配置让近期注意力组的权重高于长期总注意力组。

## 缺失信号

缺失信号不会被静默假装成真实的 `0`，而是记录在 `missing_signals` 中。排序时，缺失信号不提供正向证据；这表示“当前监控来源没有观察到这个证据”，不表示论文真实世界里一定没有关注度。

这个选择偏保守，适合当前阶段：PaperScout 推荐的是“监控来源中的高关注论文”，不是全网客观最高关注论文。
