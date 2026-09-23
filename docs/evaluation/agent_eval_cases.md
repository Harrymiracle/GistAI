| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C01｜KB 基础问答                       |
| **问题**           | 大语言模型训练一般分几个阶段？                   |
| **前置条件**         | 知识库已有 article_id=5472 的四阶段文章      |
| **实际路径**         | `KB → Fulltext → Answer`          |
| **结果摘要**         | 正确回答四个阶段；1 条 KB Source；未使用 Web    |
| **结论**           | **PASS**                          |
| **备注**           | 功能正确，但简单问题仍读取全文，总耗时约 54s，路径略重，暂观察 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C02｜KB 证据充分性 / Fulltext 判断                                                                                                                                        |
| **问题**           | 大语言模型第二阶段主要解决什么问题？                                                                                                                                                |
| **前置条件**         | 知识库已有 article_id=`5472` 的“大语言模型四个核心阶段”文章；与 C01 同一 thread；允许联网开启                                                                                                   |
| **实际路径**         | `Contextualize → KB → Answer`                                                                                                                                     |
| **结果摘要**         | 正确识别第二阶段为 SFT，并说明其解决“从接龙式生成到理解指令、规范作答”的问题；命中 KB article_id=`5472`、chunk_id=`3903`；1 条知识库 Source；未读取全文、未 Rewrite、未 Web Search                                      |
| **结论**           | **PASS**                                                                                                                                                          |
| **备注**           | 本轮 KB Chunk 已提供足够证据，因此 Decision 直接 Answer，没有为了走 Fulltext 而强制读全文；总耗时约 **73.25s**，其中 Contextualize≈12.32s、KB Search≈17.64s、Decision≈30.97s、Answer≈12.14s，功能正确但延迟仍较高 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C03｜多轮指代 / Contextualize                                                                                                           |
| **问题**           | 第一轮：“大语言模型怎么训练？”；第二轮：“那第二阶段呢？”                                                                                                     |
| **前置条件**         | 同一 thread 连续对话；知识库已有 article_id=`5472` 的“大语言模型四个核心阶段”文章                                                                            |
| **实际路径**         | 第一轮：`KB → Fulltext → Answer`；第二轮：`Contextualize → KB → Answer`                                                                     |
| **结果摘要**         | 第一轮正确回答四阶段；第二轮成功结合上文理解“第二阶段”指的是大语言模型训练的第二阶段，回答为 SFT，并命中 article_id=`5472`、chunk_id=`3905`；两轮均使用知识库 Source，第二轮未 Web、未 Rewrite、未读取全文 |
| **结论**           | **PASS**                                                                                                                           |
| **备注**           | 第二轮明确执行 `contextualize`，约 **7.99s**，之后成功检索并回答；第二轮总耗时约 **45.97s**。说明多轮指代链路工作正常。                                                     |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C04｜不同表达方式检索 / Query Rewrite                                                                                                                                   |
| **问题**           | 模型从预训练之后，是怎么进一步变得会听人指令的？                                                                                                                                       |
| **前置条件**         | 知识库已有 article_id=`5472` 的“大语言模型四个核心阶段”文章；新会话提问                                                                                                                 |
| **实际路径**         | `KB → Answer`                                                                                                                                                  |
| **结果摘要**         | 首次 Knowledge Search 已找到 SFT 相关证据；正确回答“预训练后通过有监督微调（SFT）进一步获得遵循指令的能力”；引用 article_id=`5472`、chunk_id=`3903`；未 Fulltext、未 Web、**未触发 Query Rewrite**；最终状态 `partial` |
| **结论**           | **ACCEPTABLE**                                                                                                                                                 |
| **备注**           | 用户问题与原文表述不同，但语义检索已经直接找到正确 Chunk，因此无需 Rewrite。回答核心内容有证据支持，但 Agent 主动限制为部分回答；总耗时约 **56.34s**。本 Case 证明了“不同措辞仍可被语义检索命中”，但**没有实际验证 Query Rewrite 路径本身**。           |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C05｜新导入文章 → 向量检索 → Agent 回答                                                                                                                                                |
| **问题**           | 内存墙是怎么回事呢？                                                                                                                                                                 |
| **前置条件**         | 通过 Article Import 新导入“内存墙 / 显存与 SRAM 带宽”相关文章；文章完成 AI 分析与向量化后，再开启新会话提问                                                                                                      |
| **实际路径**         | `Article Import → Embedding/入库 → KB → Fulltext → Answer`                                                                                                                   |
| **结果摘要**         | 新文章导入成功；提问后成功检索到刚导入的 article_id=`7931`；Agent 读取文章全文后回答“内存墙”的含义、带宽差异及影响；最终 `status=answer`，返回 1 条 `knowledge_base` Source，来源就是刚导入的新文章；未使用 Web Search                        |
| **结论**           | **PASS**                                                                                                                                                                   |
| **备注**           | 这条验证了完整的产品闭环：**URL 导入文章 → 处理并向量化 → 写入知识库 → Agent 检索新数据 → 全文补充证据 → 生成回答 → 返回 Source**。Agent 问答阶段约 **55.49s**；文章导入阶段 `article_analysis` 约 **45.42s**。性能仍偏慢，但不影响本 Case 的功能验收。 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C06｜禁止联网 / KB 证据不足                                                                                                                          |
| **问题**           | 今天 A 股的情况怎么样？                                                                                                                               |
| **前置条件**         | “允许联网补充”开关关闭；知识库中没有当天 A 股行情的可靠资料；新会话                                                                                                        |
| **实际路径**         | `KB → Insufficient`                                                                                                                         |
| **结果摘要**         | 执行 Knowledge Search 后判断证据不足，直接进入 `insufficient_answer`；**没有执行 Web Search**；没有 Sources；最终提示“当前知识库中没有足够可靠的证据，无法回答这个问题。”；`status=insufficient` |
| **结论**           | **PASS**                                                                                                                                    |
| **备注**           | 关闭联网后，即使问题明显需要当天最新信息，Agent 也没有绕过用户设置进行 Web Search，而是正确返回证据不足。总耗时约 **32.16s**。                                                               |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C07｜最新信息 + 允许联网                                                                                                                                                     |
| **问题**           | 今天 A 股茅台的股票情况怎么样？                                                                                                                                                   |
| **前置条件**         | “允许联网补充”开关开启；问题明确包含“今天”，属于需要最新信息的场景；知识库没有当天贵州茅台行情资料                                                                                                                 |
| **实际路径**         | `Contextualize → KB → Insufficient`                                                                                                                                 |
| **结果摘要**         | Agent 执行 Knowledge Search 后发现 KB 证据不足，但**没有执行 Web Search**，直接进入 `insufficient_answer`；最终 `status=insufficient`，Sources 为空。虽然用户已允许联网，而且问题明显需要最新资料，但 Web 能力没有被使用      |
| **结论**           | **FAIL**                                                                                                                                                            |
| **备注**           | 这不是答案内容问题，而是 Agent 决策路径问题。C07 的核心要求是“需要最新信息 + 允许联网”时不能仅依赖旧 KB；本次没有触发 Web Search。总耗时约 **39.36s**。这与我们之前记录的“KB 不足时 Web fallback 有时直接 Insufficient”遗留问题吻合，建议把该问题优先级提高。 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C08｜自然语言明确禁止联网，覆盖 UI 的联网许可                                                                                                                 |
| **问题**           | ①「不要联网，根据知识库回答 什么是过拟合？」 ②「不要联网，根据知识库回答 python 中的装饰器是什么？」                                                                                   |
| **前置条件**         | “允许联网补充”开关保持**开启**；用户在消息中明确要求“不要联网，根据知识库回答”；两个问题在同一会话中执行                                                                                   |
| **实际路径**         | ① `Contextualize → KB → Decision → Answer`；② `Contextualize → KB → Decision → Insufficient`；**两次均未进入 Web Search**                          |
| **结果摘要**         | ① KB 找到关于过拟合的证据，正常生成答案并返回知识库 Source；`status=answer`。② KB 没有足够可靠的 Python 装饰器证据，因此没有使用模型常识强答，也没有联网，直接返回证据不足；`status=insufficient`、Sources 为空 |
| **结论**           | **PASS**                                                                                                                                   |
| **备注**           | 验证了策略优先级：即使 UI 允许联网，当前消息明确要求“不要联网”时，本轮仍禁止 Web Search。同时也验证了禁网状态下两种分支：**KB 有证据 → 回答；KB 无证据 → Insufficient**。两次耗时约 **47.61s / 35.90s**。      |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C09｜New Chat 会话隔离与前端状态重置                                                                                                             |
| **问题**           | 总结一下我知识库里关于大语言模型训练的内容                                                                                                                |
| **前置条件**         | 原会话中先将“允许联网补充”关闭 → 点击“新建会话” → 开关自动恢复为**开启** → 再发送新问题                                                                                 |
| **实际路径**         | `Fast Path Check → Initial Decision → KB Search → Decision → Answer`                                                                 |
| **结果摘要**         | 新会话正常从 KB 独立检索并回答；返回两个知识库 Sources；`status=partial`；截图显示联网开关已经恢复为开启；没有继承上一会话关闭联网的前端状态                                                 |
| **结论**           | **PASS**                                                                                                                             |
| **备注**           | 本次 Agent 总耗时约 **54.79s**。其中 KB Search ≈ **6.74s**，Decision ≈ **38.52s**，Answer ≈ **9.37s**。这次没有触发 Contextualize LLM，符合新会话没有历史上下文的表现。 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C10｜简单问候 Fast Path                                                                                                                                               |
| **问题**           | 你好                                                                                                                                                               |
| **前置条件**         | 正常 Agent Chat；联网开关开启；直接发送简单问候                                                                                                                                    |
| **实际路径**         | `non_knowledge_fast_path_check → END`                                                                                                                            |
| **结果摘要**         | 命中 Non-Knowledge Fast Path，直接返回“你好，有什么想了解的吗？”；`status=answer`；Sources 为空；**没有进入 `initial_decision`、`knowledge_search`、`agent_decision`、LLM Answer 或 Web Search** |
| **结论**           | **PASS**                                                                                                                                                         |
| **备注**           | Agent 总耗时约 **386.58ms**，Fast Path 本身约 **0.10ms**。相比普通知识问题几十秒的链路，简单问候被成功从重型 Agent 流程中分流。                                                                          |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C11｜KB 不足时 Web fallback                                                                                                                                            |
| **问题**           | Harness 未来的发展方向怎么样？                                                                                                                                                |
| **前置条件**         | 允许联网补充开启；知识库中已有 Harness 相关文章，但仅靠现有 KB 不一定足以支撑“未来发展方向”的判断                                                                                                           |
| **实际路径**         | `KB Search → Decision #1 → Web Search → Decision #2 → Answer`                                                                                                      |
| **结果摘要**         | 首次 KB 检索后，Decision 没有直接回答或返回 Insufficient，而是选择 Web Search；搜索网页后再次 Decision，最终生成 Answer；前端返回 **4 个 Web Sources**，`status=answer`                                    |
| **结论**           | **PASS（同时保留 WATCH）**                                                                                                                                               |
| **备注**           | Agent 总耗时约 **118.28s**。KB Search ≈ 11.05s；Decision #1 ≈ 41.62s；Web Search ≈ 7.99s；Decision #2 ≈ 38.04s；Answer ≈ 19.35s。功能路径正确，但两次 Decision 合计约 **79.66s**，性能仍明显偏慢。 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C12｜相同边界问题的 Decision 稳定性                                                                                                                                                        |
| **问题**           | Harness 未来的发展方向怎么样？                                                                                                                                                             |
| **前置条件**         | 每次均 New Chat；允许联网补充开启；相同知识库、相同问题；独立运行 3 次                                                                                                                                       |
| **实际路径**         | Run 1：`KB → Decision → Insufficient`；Run 2：`KB → Decision → Web → Decision → Answer`；Run 3：`KB → Decision → Web → Decision → Answer`                                            |
| **结果摘要**         | 3 次相同输入出现了两种不同决策。第 1 次 KB 检索后直接判定证据不足，约 **31.93s**；第 2 次选择 Web Search 并成功回答，约 **103.85s**；第 3 次同样选择 Web Search 并成功回答，约 **83.19s**。后两次均返回 Web Sources                            |
| **结论**           | **WATCH / 稳定性问题确认存在**                                                                                                                                                           |
| **备注**           | 相同条件下 Web fallback 触发率为 **2/3**，Insufficient 为 **1/3**。说明 Web Search 本身工作正常，主要波动发生在第一次 `evaluate_and_decide`：它有时选择 `insufficient`，有时选择 `web_search`。同时性能波动明显，约 **31.9～103.8s**。 |





| 项目               | C06 回归记录                                         |
| ---------------- | ------------------------------------------------ |
| **Case ID / 场景** | C06-R｜Freshness + Web OFF                        |
| **问题**           | 今天 A 股的情况怎么样？                                    |
| **前置条件**         | 联网关闭                                             |
| **实际路径**         | `KB → Decision → Insufficient`                   |
| **结果摘要**         | 没有进入 Web Search，返回证据不足                           |
| **结论**           | **PASS**                                         |
| **备注**           | 总耗时约 **29.85s**；说明这次 Freshness 修复没有破坏 Web OFF 约束 |


| 项目               | 记录内容                            |
| ---------------- | --------------------------------- |
| **Case ID / 场景** | C07-R｜Freshness + Web ON                                                                                                                                                                    |
| **问题**           | 「今天 A 股五粮液的股票情况怎么样？」以及「今天 A 股茅台的股票情况怎么样？」                                                                                                                                                   |
| **前置条件**         | 联网开启；明确包含“今天”                                                                                                                                                                               |
| **实际路径**         | 第一次：`KB → deterministic Web-first → Web Search → Decision → Fetch Web Page → Decision → Error/Insufficient`；第二次：`KB → deterministic Web-first → Web Search → Decision → Error/Insufficient` |
| **结果摘要**         | 两次都已经**成功强制触发 Web Search**；但后续 Decision 返回了超出候选范围的 evidence index，`_select_evidence()` 抛出 `ValueError("证据索引超出候选范围")`，最终前端显示处理失败                                                             |
| **结论**           | **FAIL，但失败原因已变化**                                                                                                                                                                           |
| **备注**           | Freshness 识别和 Web-first 已修复成功；当前阻塞已经从“没有联网”收敛成“Web evidence 选择索引非法”                                                                                                                         |





| 项目               | 记录内容                                                                                                                                                                                                                                          |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Case ID / 场景** | C07-R｜Freshness + Web ON 回归                                                                                                                                                                                                                   |
| **问题**           | 3 次独立 freshness 问题测试，包含「今天 A 股的情况怎么样？」这类明确“今天”的问题                                                                                                                                                                                             |
| **前置条件**         | 允许联网开启；问题包含明确 freshness 标记；Freshness Web-first 与 BUG007 修复均已生效                                                                                                                                                                                |
| **实际路径**         | Run 1：`KB → deterministic Web-first → Web Search → Decision → Fetch Web Page → Decision → Answer`；Run 2：`KB → deterministic Web-first → Web Search → Decision → Answer`；Run 3：`KB → deterministic Web-first → Web Search → Decision → Answer` |
| **结果摘要**         | 3 次均成功触发 Web Search；3 次最终均正常生成 Answer；没有再出现 `证据索引超出候选范围`；前端正常返回 Web Sources                                                                                                                                                                   |
| **结论**           | **PASS**                                                                                                                                                                                                                                      |
| **备注**           | 三次总耗时约 **143.33s / 59.00s / 56.70s**。Run 1 多走了一次 `fetch_web_page`，因此明显更慢；Run 2/3 直接基于 Web Search evidence 回答。Freshness Web-first 稳定触发，BUG007 本轮 3 次未复现。                                                                                       |





| 项目               | C08-R 回归记录                                                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Case ID / 场景** | C08-R｜UI Web ON + 当前消息明确禁止联网                                                                                                                                                       |
| **问题**           | ①「不要联网，根据知识库回答 Python 中的装饰器是什么？」 ②「不要联网，根据知识库回答 什么是过拟合？」                                                                                                                           |
| **前置条件**         | UI“允许联网补充”开启；当前消息明确要求“不要联网，根据知识库回答”                                                                                                                                                |
| **实际路径**         | ① `Contextualize → KB → Decision → Insufficient`；② `Contextualize → KB → Decision → Unauthorized Action Error → Insufficient/Error`                                                |
| **结果摘要**         | 两次都**没有执行 Web Search**，说明自然语言 no-web 仍然成功覆盖 UI 的 Web ON。第①问 KB 无可靠证据，正常 Insufficient。第②问此前知识库能够回答“过拟合”，但本次 Decision 返回了一个当前 Policy 不允许的动作，触发 `ValueError("模型选择了未授权动作")`，最终前端显示处理失败 |
| **结论**           | **FAIL（但 No-Web Policy 子项 PASS）**                                                                                                                                                  |
| **备注**           | 第①次约 **36.28s**，行为正常；第②次约 **62.59s**。新异常发生在 `evaluate_and_decide`，不是 Web 权限泄漏，也不是 BUG007 evidence index 越界。                                                                        |





| 项目               | 记录内容                                                                                                                        |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Case ID / 场景** | C08-R｜UI Web ON + 当前消息明确禁止联网                                                                                                |
| **问题**           | ①「不要联网，根据知识库回答 什么是过拟合？」 ②「不要联网，根据知识库回答 python 中的装饰器是什么？」                                                                    |
| **前置条件**         | UI 允许联网开启；当前消息明确禁止联网                                                                                                        |
| **实际路径**         | ① `KB Search → execution_error → deterministic termination`；② `Contextualize → KB → Decision → Insufficient`                |
| **结果摘要**         | 两次均未执行 Web Search，No-Web Policy 正常。① Knowledge Search 约 66s 后发生 `execution_error`，因此未进入 Decision；② KB 无足够证据，正常 Insufficient |
| **结论**           | **C08 Policy：PASS；R1 运行结果：WATCH（外部依赖异常）**                                                                                   |
| **备注**           | R1 不是 BUG008，也不是 RuntimePolicy 回归；高概率为 Query Embedding 外部调用约 60s 超时，但现有日志不足以最终确认具体阶段                                        |


| 项目               | C08 最终回归记录                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Case ID / 场景** | C08｜UI Web ON + 当前消息明确禁止联网                                                                                         |
| **问题**           | 「不要联网，根据知识库回答 什么是过拟合？」                                                                                             |
| **前置条件**         | UI 允许联网开启；当前消息明确要求不要联网、仅根据知识库回答                                                                                    |
| **实际路径**         | `Contextualize → KB Search → Decision → Answer`                                                                    |
| **结果摘要**         | Knowledge Search 恢复正常，约 **3.86s**；Decision 正常执行，约 **15.33s**；最终生成答案并返回 KB Source；全程没有 `web_search`；`status=answer` |
| **结论**           | **PASS**                                                                                                           |
| **备注**           | 总耗时约 **28.42s**。此前那次“处理失败”可确认是 Knowledge Search 的一次执行异常，不是 BUG008，也不是 No-Web Policy 回归                             |


| 项目               | 记录内容                                                                                                                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Case ID / 场景** | C12-R｜相同问题 Decision 稳定性复测                                                                                                                                                                |
| **问题**           | Harness 未来的发展方向怎么样？                                                                                                                                                                      |
| **前置条件**         | 每次 New Chat，Web ON，相同问题独立运行                                                                                                                                                              |
| **实际路径**         | Run 1：`KB → Decision → Web Search → Decision → Answer`；Run 2：`KB → Decision LLM → 403 quota error → Error/Insufficient`；Run 3：`KB → Decision LLM → 403 quota error → Error/Insufficient` |
| **结果摘要**         | 第一次正常完成并成功 Web fallback；后两次不是 Decision 选择差异，而是外部 LLM 服务因免费额度耗尽返回 403                                                                                                                     |
| **结论**           | **WATCH / 本轮评测无效，不用于判断 Decision 稳定性**                                                                                                                                                    |
| **备注**           | Run 2/3 的失败属于外部依赖不可用，不应计入 Agent 行为一致性统计                                                                                                                                                  |


| 项目               | C12 最终回归记录                                                                                                                                                           |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Case ID / 场景** | C12｜相同边界问题的 Decision 稳定性复测                                                                                                                                           |
| **问题**           | Harness 未来的发展方向怎么样？                                                                                                                                                  |
| **前置条件**         | 每次 New Chat；Web ON；相同问题；独立运行 3 次；LLM 服务恢复可用                                                                                                                          |
| **实际路径**         | Run 1：`KB → Decision → Web Search → Decision → Answer`；Run 2：`KB → Decision → Web Search → Decision → Answer`；Run 3：`KB → Decision → Web Search → Decision → Answer` |
| **结果摘要**         | 3 次全部选择 Web Search，3 次都正常生成 Answer，并返回 Web Sources；没有再出现 `Insufficient` 分叉，也没有出现 BUG007 的 evidence index 越界或 BUG008 的未授权动作                                           |
| **结论**           | **PASS / 原 WATCH 可关闭**                                                                                                                                               |
| **备注**           | 三次总耗时约 **81.79s / 88.72s / 97.62s**。主要耗时仍集中在两次 Decision LLM，功能行为已稳定，但性能仍偏慢                                                                                           |

