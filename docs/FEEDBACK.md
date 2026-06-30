# 反馈循环

阶段 8 的目标是把每次阅读后的主观反馈保存下来，并生成一个轻量偏好提示。它不会假装已经有复杂的个性化推荐模型。

## 记录反馈

默认会给最近一次推荐记录保存反馈：

```bash
paperscout feedback
```

也可以显式指定分数和标签，适合脚本化运行：

```bash
paperscout feedback \
  --paper-usefulness 5 \
  --explanation-quality 4 \
  --wanted-more-math \
  --wanted-more-experiments \
  --note "希望多讲公式假设和实验失败模式"
```

如果要给指定推荐记录反馈：

```bash
paperscout feedback --record-id <record-id>
```

## 保存位置

- 推荐历史：`data/history/recommendations.jsonl`
- 反馈历史：`data/history/feedback.jsonl`
- 轻量偏好档案：`data/history/profile.json`

这些文件默认不提交到 Git。

## 字段含义

- `paper_usefulness`：论文有用程度，1 到 5。
- `explanation_quality`：讲解质量，1 到 5。
- `too_basic`：讲解是否偏基础。
- `too_advanced`：讲解是否偏难。
- `wanted_more_math`：后续是否希望多讲数学定义和推导。
- `wanted_more_experiments`：后续是否希望多讲实验设计和消融。
- `wanted_more_code_reproducibility`：后续是否希望多讲代码和可复现性。
- `note`：自由文本备注。

## 轻量偏好

每次保存反馈后，PaperScout 会根据全部反馈重算 `profile.json`：

- 高分论文会贡献后续偏好方向。
- “多讲数学 / 实验 / 可复现性”等标签会影响讲解风格提示。
- 最近备注会被整理成自由文本偏好。

后续运行 `paperscout recommend` 时，CLI 会打印这些反馈摘要，提醒当前偏好。但这只是启发式提示，不会替代论文质量判断，也不会自动证明某个方向更值得读。
