如果 MVP_IMPLEMENTATION_PLAN.md 与你的默认习惯冲突，以该文档为最高优先级，不要自行替换技术方案。
你现在位于一个空的项目文件夹中。
项目目标和完整实施计划已经写在：
docs/MVP_IMPLEMENTATION_PLAN.md
请先完整阅读这个文件，并严格遵守其中的：
- 技术选型
- 项目结构
- Codex 执行规则
- Phase 顺序
- 每阶段验收标准
当前任务：
只执行 Phase 0：项目初始化。
要求：
1. 不要进入 Phase 1。
2. 不要提前实现数据库、Crawler、AI、RAG、业务页面等后续功能。
3. 使用 Monorepo 结构。
4. 初始化 React + TypeScript 前端。
5. 初始化 FastAPI 后端。
6. 创建根目录必要文件和目录，包括：
   - apps/web
   - apps/server
   - docs
   - infra
   - .gitignore
   - .env.example
   - README.md
7. 前端保证能够正常启动。
8. 后端实现最小 /health 接口，并保证能够正常启动。
9. 如果当前目录还没有 Git 仓库，则执行 git init。
10. 不要创建真实 .env 密钥，不要写入任何真实 API Key。
11. 不要提交 node_modules、.venv、.env。
12. 先检查当前环境中的 Node、npm、Python、Git 是否可用；如遇到缺失依赖或命令失败，先说明问题并采用最小改动修复。
13. 所有复杂业务逻辑暂时不要实现。
14. 完成后实际运行必要验证，不要只创建文件。
完成后请只向我汇报：
1. Phase 0 是否完成
2. 创建了哪些主要文件和目录
3. 执行了哪些命令
4. 前端启动验证结果
5. FastAPI /health 验证结果
6. Git 状态是否正常
7. 是否存在需要我手动处理的问题
8. 是否满足 Phase 0 验收标准
完成后停止，不要继续执行 Phase 1。