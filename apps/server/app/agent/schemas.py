from enum import StrEnum


class AgentAction(StrEnum):
    """后续 Agent 流程允许使用的动作类型。"""

    KNOWLEDGE_SEARCH = "knowledge_search"
    REWRITE_QUERY = "rewrite_query"
    WEB_SEARCH = "web_search"
    GET_ARTICLE_CONTENT = "get_article_content"
    FETCH_WEB_PAGE = "fetch_web_page"
    ANSWER = "answer"
    PARTIAL_ANSWER = "partial_answer"
    INSUFFICIENT = "insufficient"


class EvidenceStatus(StrEnum):
    """证据是否足以回答问题的基础状态。"""

    UNKNOWN = "unknown"
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
