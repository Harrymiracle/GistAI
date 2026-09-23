from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


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


class AIArticleResult(BaseModel):
    """LLM 文章分析结果的可信结构。"""

    model_config = ConfigDict(extra="forbid")

    one_sentence_summary: SummaryText
    key_points: list[KeyPointText] = Field(min_length=1, max_length=10)
    detailed_summary: SummaryText
    tags: list[TagText] = Field(min_length=1, max_length=10)

    @field_validator("tags", mode="after")
    @classmethod
    def deduplicate_tags(cls, tags: list[str]) -> list[str]:
        """保持模型顺序并移除完全同名的重复标签。"""

        return list(dict.fromkeys(tags))
