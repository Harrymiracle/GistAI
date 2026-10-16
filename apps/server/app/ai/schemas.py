from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


SummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]
KeyPointText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
TagText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class AIArticleSummaryResult(BaseModel):
    """LLM 文章摘要结果的可信结构。"""

    model_config = ConfigDict(extra="forbid")

    one_sentence_summary: SummaryText
    key_points: list[KeyPointText] = Field(min_length=1, max_length=10)
    detailed_summary: SummaryText


class AIArticleTopicResult(AIArticleSummaryResult):
    """LLM 文章摘要与主题候选的清洗后结构。"""

    topics: list[TagText] = Field(default_factory=list)
    suggested_topic: TagText | None = None
