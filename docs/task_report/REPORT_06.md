Phase 6 的代码实现与 Mock 验收已完成；真实百炼验证因本机缺少配置而未执行。未进入 Phase 7。
修改文件
核心实现：
- [client.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\ai\\client.py)：OpenAI-compatible LLM Client。
- [service.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\ai\\service.py)：Prompt 构造、JSON 解析和结构化校验。
- [schemas.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\ai\\schemas.py)：AI 结果 Pydantic Schema。
- [errors.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\ai\\errors.py)：安全的 LLM 异常类型。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：同步抓取→AI pipeline、状态和标签持久化。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：AI Service 依赖注入。
- [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：创建文章及手动正文成功后进入 AI。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\models\\article.py)：增加只读 Tags ORM 关系。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\article.py)：Article Detail 返回标签。
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：LLM 配置。
- [requirements.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements.txt)：增加 openai。
- [.env.example](E:\\practice\\projects\\GistAI\\.env.example)：增加空配置和超时配置，没有写入密钥。
测试：
- [test_ai_service.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_ai_service.py)：Prompt、Schema、客户端错误映射。
- [test_ai_pipeline.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_ai_pipeline.py)：AI 状态、持久化和标签测试。
- 更新既有测试与 [conftest.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\conftest.py)，统一使用 Mock AI，不消耗 Token。
LLM Client / AI Service
调用层次：
ArticleService
→ AIService
→ OpenAICompatibleClient
→ 百炼 OpenAI-compatible Chat Completions
- Client 只负责模型调用及错误转换。
- AI Service 负责 Prompt、JSON 解析和 Pydantic 校验。
- Router 只做依赖注入和 Service 调用。
- 未引入 LangChain、LangGraph 或 Agent。
配置全部来自本机 .env：
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=60
实际 LLM_MODEL：未配置。没有读取、输出或记录任何真实 API Key。
Prompt 与结构化 Schema
Prompt 明确要求：
- 只依据文章正文。
- 不联网补充、不猜测、不虚构。
- 忽略正文中的提示注入内容。
- 默认简体中文。
- 只返回 JSON。
结构严格校验：
- one_sentence_summary：非空字符串。
- key_points：1～10 个非空字符串。
- detailed_summary：非空字符串。
- tags：1～10 个标签，每个最多 100 字符。
- 禁止额外字段。
- 标签自动去除完全同名重复项。
非法 JSON、缺字段、错误类型、空结果均不会保存半成品。
状态与持久化
仅当 fetch_status=completed 且存在 clean_content 时执行 AI。
成功：
ai_status=completed
ai_error=null
embedding_status=pending
status=processing
保存一句话总结、核心观点、详细摘要和标签。不会提前把 Article 标记为最终完成。
失败：
ai_status=failed
status=partial_failed
embedding_status=pending
保留原有 clean_content、content_hash 和 fetch_status=completed，错误字段只保存安全信息。
标签处理
- 按 user_id + name 复用现有标签。
- Pydantic 层去重，数据库唯一约束继续兜底。
- AI 结果完全校验成功后，才原子替换当前 Article 的标签关联。
- AI 失败时不会清除旧标签或保存部分标签。
- 未实现 Tags CRUD、标签筛选等 Phase 7 功能。
实施计划将 regenerate-ai 放在 Phase 12，因此本阶段未提前增加该接口。
错误处理
已覆盖：
- 配置缺失。
- 请求超时。
- 网络连接失败。
- HTTP 401。
- HTTP 429。
- HTTP 5xx。
- 空响应。
- 非法 JSON。
- 缺字段、错误类型和额外字段。
API 不会暴露 Authorization、API Key、内部路径或 traceback。
测试结果
执行：
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_ai_service.py --ignore=tests/test_ai_pipeline.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\python.exe -m compileall -q app tests
git diff --check
git ls-files .env
结果：
- 全量测试：72 passed。
- Phase 0～5 独立回归：44 passed。
- 新增 Phase 6 测试：28 个。
- pip check：No broken requirements found。
- 编译检查：通过。
- git diff --check：通过。
- .env 未被 Git 跟踪。
- 唯一警告是既有 FastAPI TestClient 的 httpx2 迁移提示，不影响验收。
Mock 摘要示例：
{
  "one_sentence_summary": "文章解释了安全的结构化摘要流程。",
  "key_points": [
    "正文是唯一事实来源",
    "模型结果必须经过 Schema 校验"
  ],
  "detailed_summary": "文章介绍了如何调用模型、校验结果并安全地持久化摘要和标签。",
  "tags": ["AI", "内容处理"]
}
真实百炼验证
未执行。检查确认缺少：
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL
按照要求，没有猜测配置或发起真实调用。因此目前还没有可报告的真实百炼摘要及 PostgreSQL 入库结果。补齐本机 .env 后需要重新执行这一项人工验收。
数据库与 Alembic
- 未修改数据库表结构。
- 未新增或修改 Alembic migration。
- 当前版本：ad5ad692fa18 (head)。
- alembic check：No new upgrade operations detected。
- 新增依赖：openai 2.54.0。
Phase 6 Checklist
- OpenAI-compatible Client
- Base URL / Key / Model 配置化
- 中文受控 Prompt
- Pydantic 结构校验
- 三类摘要结果持久化
- AI 标签持久化及复用
- AI 成功/失败状态流转
- 安全错误处理
- Mock 测试不消耗 Token
- Phase 0～5 全量回归
- pip 与 Alembic 验收
- 真实百炼调用：等待本机补齐三项 LLM 配置
已停止开发，未进入 Phase 7。



Phase 6 最终验收报告
Phase 6 已完整验收通过。
真实百炼验证
- 实际模型：qwen3.7-plus-2026-05-26
- 真实 OpenAI-compatible API 调用：成功
- 结构化 JSON 校验：成功
- PostgreSQL 持久化后二次读取：成功
实际生成结果：
- 一句话总结：成功
- 核心观点：成功，共 9 条
- 详细摘要：成功
- 标签：成功，共 8 个
标签示例：人工智能应用、系统可靠性、数据校验、持久化策略、状态管理。
数据库状态验证
全部符合预期：
fetch_status=completed
ai_status=completed
ai_error=null
embedding_status=pending
status=processing
同时确认：
- clean_content 未被修改。
- content_hash 未被破坏。
- 独立重新计算 SHA256，与数据库值完全一致。
- 摘要、核心观点、详细摘要和标签均已实际写入 PostgreSQL。
验收数据清理
- 临时 Article 已删除。
- 本次新增且未被其他文章引用的临时标签已删除。
- 数据库复查确认验收 Article 不再存在。
- 未残留验收数据。
Secret / Git 检查
- 未修改或输出 .env。
- API Key 未出现在命令输出或最终报告中。
- Git 已跟踪文件中的 API Key 匹配数：0
- 项目日志中的 API Key 匹配数：0
- .env 未被 Git 跟踪。
- .env 已被 .gitignore 正确忽略。
最终测试
pytest:          72 passed
pip check:       No broken requirements found
alembic current: ad5ad692fa18 (head)
alembic check:   No new upgrade operations detected
测试中仅有既存的 FastAPI TestClient/httpx2 弃用提示，不影响功能或验收。
本次未修改任何业务代码或数据库结构。Phase 6 最终验收完成，未进入 Phase 7。