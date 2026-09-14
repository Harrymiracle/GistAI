你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第五批开发任务。

Phase 16 / Task 4 已完成。

当前 Agent Graph 已具备：

```text
START
→ initialize
→ initial_decision
→ knowledge_search
→ evaluate_and_decide
   ├─ ANSWER → generate_answer → END
   ├─ REWRITE_QUERY → rewrite_query → knowledge_search
   ├─ WEB_SEARCH → web_search → evaluate_and_decide
   └─ INSUFFICIENT → insufficient_answer → END
```

当前已有能力：

* Conversation-level / Run-level State
* Runtime Context
* Knowledge Search
* Query Rewrite
* Evidence Evaluation
* Structured Decision
* `allowed_actions`
* Conditional Edge
* Answer / Partial / Insufficient
* Intent Classification
* `allow_web`
* `requires_freshness`
* Web Search
* KB Evidence / Web snippet Evidence 区分
* 单次 Web Search Budget
* InMemory checkpoint
* 自动化测试

当前完整后端测试基线：

```text
254 passed
```

---

# 一、本次任务目标

本次只实现：

> **Task 5：为 Agent 增加“读取全文”的能力。**

包括两个只读 Tool：

```text
get_article_content(article_id)
```

用于读取：

> 当前用户个人知识库中已经保存的文章完整正文。

以及：

```text
fetch_web_page(url)
```

用于读取：

> Web Search 结果对应的外部网页正文。

目标是解决 Task 4 当前的核心限制：

```text
Knowledge Search
→ 只有相关 chunk

Web Search
→ 只有 title + snippet
```

Task 5 后，Agent 可以在需要时进一步：

```text
搜索
→ 判断证据不够
→ 读取正文
→ 再评估
→ 回答
```

---

# 二、严格任务边界

本次不要实现：

* `save_to_knowledge_base`
* 自动保存 Web 文章
* PostgreSQL checkpoint
* Long-term Memory
* Multi-Agent
* Planner / Executor
* Reflection
* 前端页面
* 新 Agent HTTP UI
* 新数据库表
* 新 Alembic migration
* 通用 Tool Registry 大框架
* 全站爬虫
* 多页递归抓取
* Link crawling
* Browser Agent
* 自动点击网页
* 登录态网站抓取
* Side-effect Tool

本次只增加：

> **两种受控只读全文读取能力。**

完成后停止，不继续 Task 6。

---

# 三、核心设计原则

继续遵守：

> LangGraph 负责 orchestration，业务 Service 负责能力实现。

Node 不应该重新实现：

* 数据库文章查询
* HTTP 抓取
* Playwright fallback
* 正文提取
* SSRF 校验
* 内容清洗

这些能力 Stage 1～9 已经存在。

Task 5 必须优先复用已有实现。

---

# 四、现有能力必须先检查

开发前先阅读当前项目已有：

## Knowledge Base

* Article Model
* Article Service
* Article Detail / Content 查询
* 用户隔离逻辑
* `clean_content`
* article ownership / user_id 校验

确认：

> 哪个 Service 最适合被 `get_article_content` 直接复用。

不要通过 HTTP Router 调自己后端 API。

优先：

```text
Agent Tool
→ Service
→ Repository / DB
```

---

## Web Fetch

检查 Stage 3 / Stage 4 已有：

```text
URL validation
→ SSRF protection
→ HTTP fetch
→ Playwright fallback
→ extract
→ clean
→ clean_content
```

Task 5 必须复用这条已有抓取主链。

不要为 Agent 再写第二套网页抓取器。

---

# 五、为什么要有全文读取

Task 4 中：

```text
Web snippet
```

只能作为：

> weak / preliminary evidence

而：

```text
Knowledge Search chunk
```

虽然比 snippet 更可靠，但有时只命中了文章局部。

因此 Agent 应该可以决定：

```text
“当前候选文章相关，但 chunk 不够”
→ READ_ARTICLE
```

或者：

```text
“Web Search 找到了可能相关页面，但 snippet 不足”
→ FETCH_WEB_PAGE
```

然后再进入：

```text
evaluate_and_decide
```

---

# 六、AgentAction 扩展

扩展现有：

```text
AgentAction
```

加入概念：

```text
READ_ARTICLE
FETCH_WEB_PAGE
```

如果当前 Enum 命名风格更适合：

```text
GET_ARTICLE_CONTENT
FETCH_WEB_PAGE
```

也可以。

重点是不要创建重复 Action Enum。

---

# 七、get_article_content Tool

实现：

```text
get_article_content(article_id)
```

职责：

> 读取当前用户自己的知识库文章正文。

输入：

```text
article_id
```

不要允许：

* 任意 user_id
* 任意 database filter
* SQL 参数
* 直接传全文

用户身份必须来自：

```text
AgentContext / Runtime Context
```

---

# 八、get_article_content 权限

这是强制要求。

Agent 不能因为知道：

```text
article_id
```

就读取任意用户的数据。

Service 层必须确保：

```text
article_id
+
current_user_id
```

共同约束文章查询。

如果：

* article 不存在
* 不属于当前用户
* 不可访问

则统一返回安全的：

```text
not found / unavailable
```

不要泄露：

> “这篇文章属于另一个用户”。

---

# 九、READ_ARTICLE 来源限制

Agent 不能随便生成：

```text
article_id
```

然后读取。

第一版要求：

> 只能读取当前 Run 中已经通过 Knowledge Search 返回过的 article_id。

也就是说：

```text
READ_ARTICLE
```

必须来自：

```text
kb_results
```

中的候选。

程序必须校验：

```text
requested article_id ∈ kb_results.article_id
```

避免 LLM 自由猜 ID。

---

# 十、Article Read Budget

必须设置程序硬限制。

建议：

```text
MAX_ARTICLE_READS = 2
```

含义：

> 一个 Agent Run 最多读取两篇知识库文章全文。

原因：

* 防止上下文膨胀
* 防止循环
* 控制 latency
* 控制数据库读取和后续 LLM token

必须在：

```text
allowed_actions
```

和：

```text
get_article_content Node
```

双层限制。

---

# 十一、Article Content Result

不要直接返回 ORM Entity。

定义最小、结构化、可序列化结果。

至少包含：

```text
article_id
title
clean_content
```

如果已有：

```text
url
author
published_at
```

且后续回答有价值，可包含。

但不要把无关数据库字段全部暴露给 Agent。

---

# 十二、fetch_web_page Tool

实现：

```text
fetch_web_page(url)
```

职责：

> 读取已通过 Web Search 得到的外部网页全文。

必须复用现有：

```text
URL validation
SSRF
HTTP
Playwright fallback
extract
clean
```

不要：

```text
requests.get(url)
```

或重新写一套简单抓取逻辑绕开现有安全体系。

---

# 十三、URL 来源限制

Agent 不得自由生成任意 URL 并要求抓取。

第一版要求：

> `fetch_web_page` 只能读取当前 Run 的 `web_results` 中已经出现过的 URL。

必须程序校验：

```text
requested_url ∈ web_results.url
```

这点和：

```text
READ_ARTICLE
```

的 article_id 约束保持一致。

---

# 十四、SSRF

必须继续复用现有 SSRF 防护。

包括已有项目已经覆盖的：

* localhost
* loopback
* private IP
* metadata address
* 非法 scheme
* redirect 后安全检查
* Playwright navigation protection

Task 5 不得因为 Agent Tool 而绕过这些安全规则。

---

# 十五、Web Page Read Budget

建议：

```text
MAX_WEB_PAGE_READS = 2
```

一个 Agent Run 最多读取：

```text
2 个外部网页正文
```

必须程序硬限制。

同时进入：

```text
tool_call_counts["fetch_web_page"]
```

---

# 十六、State

Task 5 当前已有：

```text
article_contents
web_page_contents
```

本次正式使用。

---

## article_contents

存储本轮已读取的知识库文章。

结构化，例如：

```text
article_id
title
content
```

---

## web_page_contents

存储本轮已抓取的外部网页正文。

例如：

```text
url
title
content
source
published_at
```

---

这些都属于：

> Run-level State

新用户问题开始时必须清空。

不要跨新 Run 保存。

---

# 十七、不要把无限全文直接塞给 LLM

这是本 Task 的重要要求。

即使 Tool 成功拿到：

```text
10,000
20,000
50,000 字
```

也不要直接全部放进：

```text
evaluate_and_decide
generate_answer
```

必须增加一个最小：

> **temporary chunking + relevance selection**

流程概念：

```text
Full Article / Web Page
↓
临时切块
↓
根据 current_query 做相关片段选择
↓
selected full-text evidence
↓
LLM
```

---

# 十八、全文临时 Chunk

优先复用项目已有：

```text
TokenChunker
```

或已有 chunk 逻辑。

不要另外写一套毫无必要的新算法。

但这次的临时 chunk：

> 不需要写回数据库。

即：

```text
Full Content
→ Temporary Chunks
→ Select Relevant Chunks
→ Context
```

不是：

```text
Full Content
→ article_chunks table
```

---

# 十九、全文 Evidence Selection

第一版不要求新增 Reranker。

可以采用最小实现：

* 复用现有 Embedding + similarity
* 或已有 chunk selection service
* 或受控 lexical / semantic selection

优先复用现有能力。

目标只是：

> 不把全文全部塞给 LLM。

---

# 二十、Context Budget

必须有上下文大小限制。

建议设计一个明确常量或配置，例如：

```text
MAX_FULLTEXT_CONTEXT_TOKENS
```

第一版可以在大约：

```text
6000～10000 tokens
```

范围选择合理值。

不要把这个数字写死散落在多个 Node 中。

---

# 二十一、Tool Result ≠ LLM Context

必须明确区分三个东西：

```text
Tool Result
```

可能包含完整 clean_content。

```text
Agent State
```

可以暂时保存结构化全文结果。

```text
LLM Context
```

只能拿经过相关性筛选和 token budget 控制后的 Evidence。

不要把：

> Tool 返回了全文

等同于：

> 所有全文都必须送给模型。

---

# 二十二、Decision Schema 扩展

Task 3 / Task 4 当前 Decision 已经可以选择：

* KB result indexes
* Web result indexes

Task 5 需要支持选择：

```text
article_id / article result
```

进行全文读取，以及：

```text
web URL / web result index
```

进行网页读取。

推荐不要让 LLM直接返回任意 ID / URL。

优先让 LLM返回：

```text
kb_result_index
```

和：

```text
web_result_index
```

然后程序从当前 State 映射成：

```text
article_id
url
```

更安全、更容易校验。

---

# 二十三、allowed_actions

程序计算必须考虑：

```text
kb_results
web_results
article_contents
web_page_contents
article_read_count
web_page_read_count
last_tool_error
```

---

例如：

有 KB candidates，但 Evidence 不足且尚未读全文：

```text
READ_ARTICLE
```

可以进入 allowed_actions。

---

有 Web Search Results，但 snippet 不足且 Web Page Read Budget 还有：

```text
FETCH_WEB_PAGE
```

可以进入。

---

预算耗尽：

对应 Action 必须移除。

---

# 二十四、推荐决策优先级

不要写死所有行为，但 Prompt 可以给合理倾向：

```text
KB chunk 足够
→ ANSWER
```

```text
KB chunk 看起来相关但信息不完整
→ READ_ARTICLE
```

```text
KB 不够
→ Rewrite / Web Search
```

```text
Web snippet 足够支持简单事实
→ ANSWER
```

```text
Web snippet 指向相关页面但不足以支持复杂回答
→ FETCH_WEB_PAGE
```

```text
读取全文后
→ 再 Evaluate
```

---

# 二十五、Graph 目标结构

最终 Graph 可以类似：

```text
START
↓
initialize
↓
initial_decision
↓
knowledge_search
↓
evaluate_and_decide
   │
   ├─ ANSWER
   │    ↓
   │ generate_answer
   │    ↓
   │   END
   │
   ├─ REWRITE_QUERY
   │    ↓
   │ rewrite_query
   │    ↓
   │ knowledge_search
   │
   ├─ WEB_SEARCH
   │    ↓
   │ web_search
   │    ↓
   │ evaluate_and_decide
   │
   ├─ READ_ARTICLE
   │    ↓
   │ get_article_content
   │    ↓
   │ select_fulltext_evidence
   │    ↓
   │ evaluate_and_decide
   │
   ├─ FETCH_WEB_PAGE
   │    ↓
   │ fetch_web_page
   │    ↓
   │ select_fulltext_evidence
   │    ↓
   │ evaluate_and_decide
   │
   └─ INSUFFICIENT
        ↓
      insufficient_answer
        ↓
       END
```

可以根据实际实现把：

```text
select_fulltext_evidence
```

合并进 Tool Adapter / Service。

不强制一定做独立 Node。

但职责必须存在。

---

# 二十六、Conditional Edge 继续保持简单

Router 继续：

```text
只读取 next_action
```

不要在 Router：

* 查询 DB
* 抓网页
* 算 Embedding
* 判断权限
* 判断预算
* 调 LLM

这些都在 Node / Policy / Service 完成。

---

# 二十七、get_article_content Error

区分：

## 正常不可用

例如：

```text
文章不存在
当前用户无权访问
```

安全处理。

不要泄露其他用户信息。

---

## Execution Error

例如：

```text
DB unavailable
```

写入：

```text
last_tool_error
```

并进入安全终止或其他合法 Action。

---

# 二十八、fetch_web_page Error

继续区分：

## Validation Error

例如：

* URL 不在当前 web_results
* 非 HTTP/HTTPS
* SSRF 拒绝

不要 blind retry。

---

## Fetch Error

例如：

* timeout
* 403
* 5xx
* HTTP + Playwright 都失败

使用现有抓取错误模型。

不要泄露内部堆栈。

---

# 二十九、Tool Call Count

增加：

```text
tool_call_counts["get_article_content"]
tool_call_counts["fetch_web_page"]
```

只要真正执行 Tool，就：

```text
step_count += 1
tool_call_counts[...] += 1
```

Validation 阶段即被拒绝、根本未执行业务 Tool 时：

> 不应计为真实 Tool Call。

和 Task 4 规则保持一致。

---

# 三十、重复读取

同一 Run 中已经读取过：

```text
article_id = X
```

则不要再次调用 DB 全文读取。

同理已经抓取：

```text
url = Y
```

不要再次 fetch。

程序应该：

* 移除对应 Action candidate
* 或直接复用已缓存到 State 的内容

不要浪费预算。

---

# 三十一、Evidence 类型

Task 5 后至少存在四类 Evidence：

```text
KB Search Chunk
Web Search Snippet
KB Full-text Selected Chunk
Web Full-text Selected Chunk
```

需要明确：

> Full-text selected evidence 的可靠性通常高于 Search Snippet。

但仍然必须根据实际文本回答。

不要建立复杂 Evidence Scoring Framework。

---

# 三十二、Sources

如果最终回答使用了知识库全文 Evidence：

Source 应回到：

```text
article_id
title
```

如果能保留对应 chunk / temporary section reference，也可以。

---

如果使用 Web Full-text：

Source 应包含：

```text
title
url
source
published_at
source_type="web"
```

最终 sources 必须来自：

> 实际使用过的 Evidence。

---

# 三十三、Answer Grounding

`generate_answer` 必须能够接收：

```text
KB Search Evidence
Web Snippet Evidence
KB Full-text Evidence
Web Full-text Evidence
```

但仍遵守：

> Answer only from supplied evidence.

尤其：

如果已抓网页全文：

> 只能依据真正抓取到的正文，而不是搜索摘要之外继续自由补全。

---

# 三十四、Freshness

对于：

```text
requires_freshness=True
```

如果已经 Web Search，但 snippet 不足：

应优先允许：

```text
FETCH_WEB_PAGE
```

读取真实页面。

不要因为旧 KB Article Full Text 很详细就忽略“最新”要求。

---

# 三十五、Task 5 的循环必须有界

Task 5 增加 Tool 后，必须重新证明 Graph 不可能无限循环。

至少已有：

```text
max_rewrites = 1
max_web_searches = 1
```

本次增加：

```text
max_article_reads = 2
max_web_page_reads = 2
```

并禁止同一 article/url 重复读取。

因此 Agent 必须最终：

```text
ANSWER
PARTIAL
INSUFFICIENT
```

结束。

---

# 三十六、测试要求

至少覆盖以下路径。

## Test 1：KB Chunk 足够

Evidence 已足够。

验证：

```text
READ_ARTICLE
```

不执行。

---

## Test 2：KB Chunk 不完整 → Read Article

Knowledge Search 返回相关 chunk。

Decision：

```text
READ_ARTICLE
```

读取正文。

经过全文片段选择后重新 Evaluate。

最终：

```text
ANSWER
```

---

## Test 3：Article Ownership

模拟：

```text
article_id
```

不属于当前用户。

验证：

* 不返回正文
* 不泄露文章存在性或 owner
* 安全结束

---

## Test 4：非法 Article ID

LLM / Decision 请求一个：

```text
kb_results
```

中不存在的 article。

程序必须拒绝。

Service 不执行。

---

## Test 5：Article Read Budget

读取两篇后再次要求：

```text
READ_ARTICLE
```

验证：

* Action 已被移除
* 不执行第三次读取
* Graph 安全终止

---

## Test 6：重复 Article Read

同一 article 已经读取。

再次要求读取：

验证不重复查询 DB。

---

## Test 7：Web Snippet 足够

Web snippet 已足够支持简单事实。

验证：

```text
FETCH_WEB_PAGE
```

不执行。

---

## Test 8：Snippet 不足 → Fetch Page

Web Search 返回相关结果。

Decision：

```text
FETCH_WEB_PAGE
```

抓取正文。

全文选片后再次 Evaluate。

最终 Answer。

---

## Test 9：URL 必须来自 web_results

尝试抓取：

```text
https://random.example.com
```

但该 URL 不在当前 Web Search Results。

必须拒绝。

---

## Test 10：SSRF

模拟：

```text
localhost
127.0.0.1
private IP
metadata endpoint
```

确保 Agent Tool 没有绕过已有 SSRF 保护。

---

## Test 11：HTTP → Playwright Fallback

使用 Stub / Fake 验证：

```text
HTTP 抓取失败
→ Playwright fallback
```

仍然复用现有 pipeline。

不要真实访问外网。

---

## Test 12：Fetch Error

HTTP + Playwright 都失败。

验证：

* last_tool_error
* 计数正确
* Graph 安全结束
* 不无限 retry

---

## Test 13：Web Page Budget

读取两页后不允许第三次。

---

## Test 14：Full-text Context Budget

构造超长文章。

验证：

> LLM Context 不会收到整篇无限文本。

最终输入受到 token / chunk 限制。

---

## Test 15：Full-text Relevance Selection

正文包含：

```text
大量无关内容
+
少量与 current_query 高度相关内容
```

验证选入 Context 的主要是相关部分。

---

## Test 16：New Run Reset

同 thread 第一轮读取过：

```text
article_contents
web_page_contents
```

第二轮新用户问题开始。

验证：

```text
article_contents = []
web_page_contents = []
read budgets reset
```

但：

```text
messages
```

继续保留。

---

# 三十七、测试隔离

默认 Agent 测试不得依赖：

* 真实 Tavily
* 真实互联网
* 真实 LLM
* 不稳定第三方页面

使用：

* Stub Article Service
* Fake Fetch Service
* Fake Reasoning Service
* Test doubles

已有真实 Fetch Pipeline 测试继续承担 Stage 3 / 4 的真实能力验证。

---

# 三十八、回归测试

至少运行：

```text
Agent tests
Fetch / Extraction tests
Semantic Search tests
RAG tests
Full backend tests
```

以及：

```text
Python compileall
pip check
git diff --check
```

如环境允许：

```text
Frontend production build
```

---

# 三十九、开发顺序

请严格按：

1. 阅读 Phase 16 当前 Agent。
2. 阅读已有 Article Service / Article ownership 查询。
3. 阅读已有 HTTP + Playwright Fetch Pipeline。
4. 确认复用入口。
5. 给出简短实现计划。
6. 扩展 AgentAction / Decision Schema。
7. 实现框架无关 Article Content Service Adapter。
8. 实现框架无关 Web Page Fetch Adapter。
9. Runtime Context 注入。
10. 实现 `get_article_content` Node。
11. 实现 `fetch_web_page` Node。
12. 增加全文临时 Chunk / relevance selection。
13. 增加 Context Budget。
14. 扩展 allowed_actions。
15. 扩展 Evidence Evaluation。
16. 更新 Conditional Route。
17. 增加 read budgets。
18. 更新 sources / grounding。
19. 增加测试。
20. 跑定向测试。
21. 跑相关回归。
22. 跑完整后端测试。
23. `git diff --check`。
24. 做代码 review。
25. 输出总结。
26. 停止。

---

# 四十、完成后必须汇报

## 1. 修改 / 新增文件

逐个说明职责。

## 2. Article Read 调用链

明确：

```text
Agent Node
→ 哪个 Adapter / Service
→ Article Service / DB
```

以及用户隔离在哪里完成。

---

## 3. Web Fetch 调用链

明确：

```text
Agent Node
→ Fetch Adapter
→ URL Validation / SSRF
→ HTTP
→ Playwright fallback
→ Extract
→ Clean
```

确认没有重新实现第二套 Fetch Pipeline。

---

## 4. Graph

展示 Task 5 后实际 Graph。

---

## 5. allowed_actions

说明：

```text
READ_ARTICLE
FETCH_WEB_PAGE
```

分别什么情况下出现。

---

## 6. Budget

说明：

```text
max_article_reads
max_web_page_reads
```

以及防止重复读取的方法。

---

## 7. Full-text Context

说明：

* Full content 是否写入 State
* 如何临时 Chunk
* 如何做 relevance selection
* Context token budget 是多少
* 为什么不会把整个长网页塞给 LLM

---

## 8. Evidence

说明四类 Evidence 如何区分：

```text
KB chunk
Web snippet
KB full-text
Web full-text
```

---

## 9. Sources

说明最终 Answer 如何生成 KB / Web 来源。

---

## 10. Error / Security

分别说明：

```text
Article not found
Unauthorized article
Illegal article id
Illegal URL
SSRF blocked
HTTP fetch failure
Playwright failure
Budget exhausted
```

如何处理。

---

## 11. 测试结果

明确：

```text
Agent tests: X passed
Fetch tests: X passed
Agent + Semantic Search + RAG: X passed
Full backend: X passed
Frontend build: passed / not run
compileall: passed
pip check: passed
git diff --check: passed
```

---

## 12. 明确未实现

至少：

```text
save_to_knowledge_base
PostgreSQL checkpoint
Long-term Memory
Multi-Agent
Frontend Agent UI
Task 6+
```

---

# 四十一、验收标准

只有同时满足以下条件，Task 5 才算完成：

* 已实现受控 `get_article_content`
* 已实现受控 `fetch_web_page`
* Article 读取仅限当前用户
* Article ID 只能来自当前 kb_results
* URL 只能来自当前 web_results
* Web Fetch 复用已有 URL validation / SSRF / HTTP / Playwright / extraction pipeline
* 没有写第二套抓取逻辑
* Full text 不会无界进入 LLM Context
* 有 temporary chunking / relevance selection
* 有明确 context budget
* READ_ARTICLE 有程序硬预算
* FETCH_WEB_PAGE 有程序硬预算
* 同一 article / URL 不重复读取
* Run-level full-text State 新问题时会 reset
* Full-text Evidence 能重新进入 evaluate_and_decide
* Answer 可以使用真实正文 Evidence
* sources 只来自实际使用 Evidence
* Tool Error 与正常无结果区分
* SSRF 不被 Agent Tool 绕过
* Graph 不可能因为全文读取形成无限循环
* 自动化测试覆盖主要路径
* 完整回归通过
* 没有提前实现 Task 6
* 完成后停止开发

完成以上内容后，请停止，不要继续实现知识库保存、PostgreSQL checkpoint、长期 Memory 或前端 Agent UI。
