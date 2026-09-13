from dataclasses import dataclass

from app.agent.knowledge_search import KnowledgeSearchProvider
from app.agent.reasoning import AgentReasoningProvider


@dataclass(frozen=True, slots=True)
class AgentContext:
    """单次 Graph 调用使用且不写入 checkpoint 的运行时依赖。"""

    knowledge_search: KnowledgeSearchProvider
    reasoning: AgentReasoningProvider
    top_k: int = 5
