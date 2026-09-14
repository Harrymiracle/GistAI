from dataclasses import dataclass

from app.agent.article_content import ArticleContentProvider
from app.agent.fulltext import FullTextEvidenceSelector
from app.agent.knowledge_search import KnowledgeSearchProvider
from app.agent.reasoning import AgentReasoningProvider
from app.agent.web_page_fetch import WebPageFetchProvider
from app.agent.web_search import WebSearchServiceProvider


@dataclass(frozen=True, slots=True)
class AgentContext:
    """单次 Graph 调用使用且不写入 checkpoint 的运行时依赖。"""

    knowledge_search: KnowledgeSearchProvider
    web_search: WebSearchServiceProvider
    reasoning: AgentReasoningProvider
    article_content: ArticleContentProvider | None = None
    web_page_fetch: WebPageFetchProvider | None = None
    fulltext_selector: FullTextEvidenceSelector | None = None
    top_k: int = 5
