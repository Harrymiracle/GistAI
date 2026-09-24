# RAG Design

GistAI 的 RAG 由知识入库、Semantic Search、Basic RAG 和 Agentic RAG 四部分组成。

核心目标不是单纯“找到相似文本”，而是：

> 从个人知识库中取得能够支撑当前回答的 Evidence。

---

## Knowledge Representation

文章正文经过清洗后进入 Chunk + Embedding 流程：

```text
clean_content
↓
Token Chunking
↓
Embedding
↓
article_chunks
↓
PostgreSQL + pgvector
```

当前默认参数：

```text
RAG_CHUNK_SIZE = 400
RAG_CHUNK_OVERLAP = 80
EMBEDDING_DIMENSION = 1024
```

Embedding 默认使用：

```text
text-embedding-v4
```

Query Embedding 与 Document Embedding 必须来自兼容的向量空间，不能只因为向量维度相同就混用不同模型。

---

## Semantic Search

语义搜索流程：

```text
Query
↓
Query Embedding
↓
pgvector cosine distance
↓
score = 1 - cosine_distance
↓
Similarity Threshold
↓
TopK
```

当前默认参数：

```text
RAG_TOP_K = 3
RAG_SIMILARITY_THRESHOLD = 0.35
```

### Threshold

Threshold 是质量底线。

如果只取 TopK，没有 Threshold，即使所有候选都不相关，也可能返回“相对最像”的内容。因此低于阈值的结果会被过滤。

### TopK

TopK 控制返回数量上限。

```text
Threshold → 质量门槛
TopK      → 数量上限
```

### Best Chunk per Article

当前检索会避免同一篇文章的大量 Chunk 挤占结果集，只保留更有代表性的候选。

这样可以提高跨文章结果的多样性，但也意味着同一文章内多 Chunk Recall 会受到一定限制。

---

## Basic RAG

Basic RAG 使用固定流程：

```text
Question
↓
Semantic Search
↓
Context
↓
LLM
↓
Answer + Sources
```

如果没有达到相似度阈值的结果，系统不会继续调用回答 LLM 用模型自身知识补事实。

```text
No valid evidence
→ Insufficient
```

这是后续 Agentic RAG 的基础约束。

---

## Context and Sources

GistAI 区分：

### Context

提供给 LLM 的内容。

### Sources

提供给应用和最终用户展示的来源。

两者应来自同一批 Evidence，并保持一致的截断和选择逻辑。

这样可以减少“模型实际使用的内容”和“页面展示的来源”之间的不一致。

---

## From Retrieval to Evidence

Semantic Search Result 只是候选。

Agentic RAG 增加：

```text
Search Result
↓
Evidence Evaluation
↓
Selected Evidence
```

因此系统允许出现：

```text
Search succeeded
but
Evidence is not sufficient
```

这时 Agent 可以继续寻找更强证据，而不是立即回答。

---

## Query Contextualization

多轮聊天中的短追问需要先补充语义上下文。

```text
Conversation
+
Current Message
↓
Contextualized Query
↓
Semantic Search
```

这样检索 Query 不依赖用户重复描述完整问题。

---

## Query Rewrite

当第一次 Search 没有获得足够 Evidence 时，可以对工作 Query 进行 Rewrite。

```text
original_query
↓
current_query
↓
rewrite
↓
new current_query
↓
search again
```

Rewrite 有明确次数限制，不作为无限自我修正循环。

---

## KB Full-text Evidence

TopK Chunk 适合召回，但不一定包含回答问题所需的完整上下文。

当 Agent 判断需要更多文章上下文时：

```text
KB Search Result
↓
Get Article Content
↓
Full-text
↓
Temporary Selection
↓
Full-text Evidence
↓
Decision
```

全文只在当前 Run 中参与证据选择，不重新写入向量数据库。

---

## Web Evidence

当知识库无法满足问题，并且用户允许联网时：

```text
Query
↓
Web Search
↓
title / URL / snippet
↓
Evidence Evaluation
```

如果 snippet 仍不足：

```text
Web Result
↓
Fetch Web Page
↓
Full-text
↓
Temporary Selection
↓
Web Full-text Evidence
```

Web Search Provider 当前使用 Tavily。

---

## Freshness

需要最新信息的问题不能只依赖历史知识库。

系统通过：

```text
requires_freshness
allow_web
```

共同决定是否需要外部最新 Evidence。

当 freshness requirement 存在时，只有 KB Evidence 并不足以满足时效性要求。

---

## Context Budget

全文读取不代表把整篇正文全部塞入 LLM。

当前系统对 Full-text Context 设置 Token Budget：

```text
AGENT_MAX_FULLTEXT_CONTEXT_TOKENS
```

默认值：

```text
8000
```

目标是控制 Context size、推理成本、无关信息干扰和 Checkpoint 膨胀。

---

## Current Retrieval Scope

当前方案重点是可解释、可控的个人知识库检索。

尚未引入：

- Reranker
- Hybrid Retrieval 的复杂融合
- ANN 专用向量数据库
- Claim-level Verification

这些能力可以在真实数据规模或检索质量要求出现明确瓶颈后再加入，而不是提前增加系统复杂度。
