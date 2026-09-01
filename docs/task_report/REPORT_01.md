1. 修改/新增文件
修改：
- [.env.example](E:\\practice\\projects\\GistAI\\.env.example)
- [requirements.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements.txt)
新增：
- [alembic.ini](E:\\practice\\projects\\GistAI\\apps\\server\\alembic.ini)
- [env.py](E:\\practice\\projects\\GistAI\\apps\\server\\alembic\\env.py)
- [script.py.mako](E:\\practice\\projects\\GistAI\\apps\\server\\alembic\\script.py.mako)
- [初始迁移](E:\\practice\\projects\\GistAI\\apps\\server\\alembic\\versions\\ad5ad692fa18_create_core_tables.py)
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)
- [base.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\db\\base.py)
- [session.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\db\\session.py)
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\models\\article.py)
- [tag.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\models\\tag.py)
- [article_tag.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\models\\article_tag.py)
- [article_chunk.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\models\\article_chunk.py)
- 相关 __init__.py
2. 数据库表结构
表	主要字段	约束和索引
articles	计划规定的来源、正文、摘要、状态、错误及时间字段	BIGINT 主键；UNIQUE(user_id, source_url)；用户+创建时间/收藏/来源/状态索引
tags	id、user_id、name、时间字段	BIGINT 主键；UNIQUE(user_id, name)
article_tags	article_id、tag_id、created_at	组合主键；两个外键均为 ON DELETE CASCADE；tag_id 索引
article_chunks	id、article_id、chunk_index、content、token_count、embedding、metadata	BIGINT 主键；文章外键级联；UNIQUE(article_id, chunk_index)；embedding VECTOR(1024)


pgvector 扩展已安装，版本为 0.8.6。
3. 执行过的主要命令
   - pip install -r requirements.txt，使用阿里云镜像
   - pip check
   - alembic revision --autogenerate -m "create core tables"
   - alembic upgrade head
   - alembic current
   - PostgreSQL 系统目录查询
   - 事务内唯一约束、外键、级联和向量维度测试
   - alembic downgrade base
   - 再次执行 alembic upgrade head
   - alembic check
   - SQLAlchemy 实际连接查询
   - compileall
   - Uvicorn 启动及 GET /health
4. 测试/验收结果
   - SQLAlchemy 2.0.52 数据库连接成功。
   - Alembic 当前版本：ad5ad692fa18 (head)。
   - alembic check：No new upgrade operations detected.
   - 迁移升级成功。
   - 迁移回滚后四张表和 vector 扩展均被移除。
   - 再次升级成功，数据库恢复到 head。
   - 四张核心表、39 个字段、10 个约束和12 个索引验证正常。
   - embedding 类型确认是 vector(1024)。
   - URL 和标签唯一约束验证通过。
   - 非法外键写入被正确拒绝。
   - 删除标签只删除关联关系，不删除文章。
   - 删除文章会级联删除关联关系和切片。
   - 约束测试数据全部回滚，没有遗留测试记录。
   - pip check 无依赖冲突。
   - FastAPI /health 返回 HTTP 200 和 {"status":"ok"}。
5. 是否满足 Phase 1 全部验收标准
是，Phase 1 全部验收标准已满足。
6. 阶段边界
已停止。未实现 Article CRUD、Crawler、AI、RAG 或业务接口，未进入 Phase 2。