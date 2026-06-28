# 数据源说明

阶段 4 增加了真实元数据采集器，并提供 `collect` 命令把采集结果导出成候选 JSON。当前目标不是一步到位全自动推荐，而是先让数据源适配器可测试、可缓存、可解释。

可以用 `collect` 命令把真实元数据源导出为候选 JSON：

```bash
paperscout collect \
  --query "AI chemistry molecular dynamics" \
  --source arxiv \
  --output data/raw/candidates.generated.json
```

导出的候选文件可以继续交给 `recommend`：

```bash
paperscout recommend --candidates data/raw/candidates.generated.json
```

## arXiv

使用 arXiv API 查询论文元数据。arXiv API 返回 Atom feed，支持 `search_query`、`start`、`max_results`、`sortBy` 和 `sortOrder` 等参数。

实现文件：

- `src/paperscout/collectors/arxiv.py`

当前把 arXiv 结果转成候选论文元数据，并记录 `source_confidence`。如果摘要里明确出现 `https://github.com/owner/repo` 形式的代码链接，会把它保存到 `extra.github_url(s)`，供后续 GitHub 信号保守匹配使用。arXiv 本身不提供近期引用、stars 或视频数量，因此不会伪造这些注意力信号。

## Semantic Scholar

使用 Semantic Scholar Graph API 的 paper search 获取论文元数据、外部 ID、引用数和开放 PDF 链接。

实现文件：

- `src/paperscout/collectors/semantic_scholar.py`

注意：Semantic Scholar 的 `citationCount` 是引用元数据，不等于最近 30 天新增引用。当前实现把它保存为 `semantic_scholar_citation_count`，不会把它伪装成 `recent_citation_count`。

如果需要强制使用 API key，可以设置：

```bash
export SEMANTIC_SCHOLAR_API_KEY=...
```

## GitHub

使用 GitHub REST API 搜索或读取 repository 元数据，用于代码关注度信号。

实现文件：

- `src/paperscout/collectors/github.py`

当前支持的信号包括 stars、forks、open issues、最近 push 时间、语言和 topics。GitHub repository 本身不是论文，因此 collector 返回的是 repository metadata，而不是论文候选。

`collect --github-query` 会搜索 GitHub repository，并且会对候选论文元数据中已经明确包含的 `github_url(s)`、`code_url(s)`、`repository_url(s)` 或 `github_full_name` 做精确读取和匹配。当前不会用论文标题和仓库名做模糊匹配，因为错配代码仓库比缺失代码信号更危险。

如果需要更高 rate limit，可以设置：

```bash
export GITHUB_TOKEN=...
```

## 缓存

所有 HTTP collector 都可以使用 `CachedHttpClient`：

- `src/paperscout/collectors/cache.py`

缓存保存在 `data/cache/http/` 下，默认被 Git 忽略。测试中通过 fake transport 注入响应，不访问真实网络。

## 当前限制

- arXiv 和 Semantic Scholar 可以合并成候选池，但只按 DOI、arXiv ID、Semantic Scholar ID 或 URL 等稳定标识合并。
- GitHub repository 和论文的匹配只做显式 repo URL/full name 匹配，不做模糊标题匹配。
- 近期注意力信号仍然不完整，尤其是“最近 30 天新增引用”这一项。
- 缓存目前是简单文件缓存，没有过期策略；需要刷新时应显式设置 `refresh=True` 或 CLI 的 `--refresh`。
- 当前 retry/backoff 只处理网络错误、`429` 和 `5xx` 这类临时失败；还没有按具体数据源的配额窗口做精细调度。
