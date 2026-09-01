请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 6，只完成 AI 摘要/核心观点/标签生成，不进入 Phase 7。

Phase 0～5 已完成并提交。开始前阅读实施计划和现有代码，运行全量测试确认基线。

【模型配置】

Provider：阿里云百炼
API：OpenAI-compatible

使用环境变量：

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

模型和 Base URL 不硬编码。真实 API Key 只从本机 .env 读取，禁止写入源码、测试、README、.env.example、日志或 Git。

具体模型通过 LLM_MODEL 配置，方便以后替换。

【目标】

clean_content
→ LLM
→ 结构化结果
→ 后端校验
→ PostgreSQL

生成：

- one_sentence_summary：一句话总结
- key_points：核心观点数组
- detailed_summary：详细摘要
- tags：少量主题标签

要求模型只依据文章正文，不联网补充或虚构信息，默认输出中文。

【架构】

保持轻量分层：

ArticleService
→ AI Service
→ LLM Client
→ 百炼 OpenAI-compatible API

Prompt 和结构化结果处理放 AI Service。
LLM Client 只负责模型调用。
不要把调用逻辑写进 Router。
不要引入 LangChain/LangGraph/Agent。

【结构化输出】

要求模型返回类似：

{
  "one_sentence_summary": "...",
  "key_points": ["...", "..."],
  "detailed_summary": "...",
  "tags": ["...", "..."]
}

使用明确的 Pydantic Schema 校验模型结果。

非法 JSON、缺字段、类型错误、空结果等均视为 AI 失败，不保存半成品。

【状态与持久化】

只有 fetch_status=completed 且存在有效 clean_content 才能执行 AI。

开始：
ai_status=processing
status=processing

成功：
- 保存 one_sentence_summary
- 保存 key_points
- 保存 detailed_summary
- ai_status=completed
- ai_error=null
- embedding_status 仍为 pending
- overall status 按现有 pipeline 语义处理，不要因为 AI 完成就提前标记最终 completed

失败：
- ai_status=failed
- 保存安全、明确的 ai_error
- clean_content/content_hash 必须保留
- fetch_status 仍为 completed
- embedding_status 仍为 pending

【标签】

AI 生成的 tags 使用现有 tags + article_tags 持久化。

要求：
- 同一 user_id 下同名标签复用
- 不产生重复标签
- AI 重跑时标签更新策略明确、安全

只做 AI 标签持久化所需逻辑，不提前实现 Phase 7 完整 Tags CRUD。

【触发】

Phase 6 继续使用当前同步 pipeline，不实现 BackgroundTasks。

文章成功获得 clean_content 后执行 AI。

如果实施计划明确要求本阶段实现：
POST /api/v1/articles/{id}/regenerate-ai
则实现；否则留到计划指定阶段，不提前扩展。

regenerate-ai 不能重新抓网页或修改 clean_content/content_hash。

【错误处理】

至少正确处理：
- LLM 配置缺失
- timeout / 网络错误
- 401
- 429
- 5xx
- 空响应
- 非法结构化输出

不得向 API 用户暴露 API Key、Authorization、traceback 或敏感请求信息。

【测试】

自动化测试必须 Mock LLM，不消耗真实 Token。

覆盖核心场景：
- 正常结构化输出及数据库持久化
- summaries/key_points/tags 正确
- tag 不重复
- AI 成功/失败状态
- AI 失败不破坏 clean_content
- 非法模型输出
- timeout / 认证 / 限流 / 服务异常
- 配置缺失
- Phase 0～5 全量回归

【真实百炼验证】

Mock 测试通过后，使用用户本机 .env 做一次真实百炼 API 验证。

如果 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 缺失，明确告诉用户缺少什么并停止真实验证，不要猜配置。

不要输出或记录真实 API Key。

验证：

clean_content
→ 百炼
→ 结构化摘要
→ PostgreSQL

通过 Article Detail 确认 summaries/key_points/tags 已入库、ai_status=completed、clean_content 保留、embedding_status=pending。

【数据库与依赖】

可以使用轻量 OpenAI-compatible SDK，例如 openai Python SDK。

原则上不修改数据库结构；确需修改只能新增 Alembic migration，不能修改历史 migration。

执行：
- 全量 pytest
- pip check
- alembic current
- alembic check

【禁止】

本阶段不要实现：
Embedding、Chunk、Semantic Search、RAG、Agent、LangChain、LangGraph、BackgroundTasks、Redis、Celery、Qdrant、完整 Tags CRUD、登录系统。

不要进入 Phase 7。

【完成报告】

完成后停止并报告：

- 修改文件
- LLM Client / AI Service 设计
- 百炼配置方式及实际 LLM_MODEL（禁止输出 Key）
- Prompt 与结构化 Schema
- AI 状态及持久化
- 标签处理
- 错误处理
- 自动化测试和 Phase 0～5 回归结果
- 真实百炼 API 验证结果及摘要示例
- pip check / Alembic 状态
- 是否修改数据库
- Phase 6 checklist
- 明确说明未进入 Phase 7

完成后停止，等待人工验收。