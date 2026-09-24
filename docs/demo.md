# Demo

本页展示 GistAI 从文章导入到知识问答的基本使用流程。

---

## Home

首页提供两个主要入口：

- 导入文章
- 打开知识助手

![GistAI Home](images/home.png)

---

## Import an Article

输入公开文章 URL 后，系统完成：

```text
URL
↓
Fetch
↓
Extract / Clean
↓
AI Summary / Tags
↓
Chunk
↓
Embedding
↓
Knowledge Base
```

导入完成后，页面会显示处理结果，并可以直接进入 Agent Chat。

![Article Import](images/article-import.png)

文章导入不仅保存 URL。进入知识库前，正文已经完成提取、AI 处理、切片和向量化，因此后续可以直接参与 Semantic Search 和 Agent Retrieval。

---

## Ask the Knowledge Assistant

知识助手优先使用个人知识库回答问题。

示例：

```text
GEO 与 SEO 的区别是什么？
```

回答区域同时展示 Sources，用户可以看到当前答案使用了哪一条知识库证据。

![Agent Chat](images/agent-chat.png)

---

## Knowledge Base Flow

典型知识库问题：

```text
Question
↓
Query Contextualization
↓
Semantic Search
↓
Evidence Evaluation
↓
Answer
```

如果当前 Chunk 不足以回答，Agent 可以继续读取对应 Article Full-text，再重新判断证据。

```text
Knowledge Search
↓
Evidence insufficient
↓
Read Article
↓
Select Full-text Evidence
↓
Evaluate Again
↓
Answer
```

---

## Follow-up Conversation

多轮聊天通过 `thread_id` 延续同一个 conversation。

前端每轮主要发送：

```text
current message
+
thread_id
```

后端通过 PostgreSQL Checkpoint 恢复会话状态，因此用户可以直接继续追问，而不需要前端重复上传完整聊天历史。

例如：

```text
第一轮：
这篇文章主要讨论什么？

第二轮：
那其中第二点具体是什么意思？
```

第二轮 Query 会先结合上下文完成 contextualization，再进入检索。

---

## Web Search

界面提供“允许联网补充”开关。

当知识库不足，并且用户允许 Web Search 时，Agent 可以：

```text
Knowledge Search
↓
Evidence insufficient
↓
Web Search
↓
Evaluate Web Evidence
↓
Answer
```

如果 Search snippet 仍不足：

```text
Web Search Result
↓
Fetch Web Page
↓
Select Full-text Evidence
↓
Evaluate Again
↓
Answer
```

---

## Freshness

对于明显要求最新信息的问题，例如：

```text
今天有什么新的变化？
当前最新版本是什么？
```

系统会识别 freshness requirement。

如果用户允许联网，Runtime Policy 会要求使用 Web Evidence，而不是仅依赖历史知识库内容。

---

## Partial / Insufficient

GistAI 不要求 Agent 每次都必须给出完整事实答案。

当达到运行预算后：

```text
Reliable evidence exists
→ Partial Answer
```

当没有可靠 Evidence 时：

```text
No reliable evidence
→ Insufficient
```

这样可以避免在知识库和 Web Evidence 都不足时，用模型自身知识强行补全。

---

## API

Agent Chat API：

```text
POST /api/v1/agent/chat
```

Request：

```json
{
  "message": "用户当前问题",
  "thread_id": "可选 UUID"
}
```

Response：

```json
{
  "thread_id": "UUID",
  "answer": "回答内容",
  "status": "answer | partial | insufficient | error",
  "sources": []
}
```

---

## Local Access

默认本地地址：

```text
Frontend:
http://localhost:8088/

FastAPI Swagger:
http://127.0.0.1:8000/docs
```

完整启动方式见项目根目录 `README.md`。
