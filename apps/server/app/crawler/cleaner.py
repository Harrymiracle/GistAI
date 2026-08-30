import html
import re
import unicodedata


HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")
EXCESSIVE_NEWLINES = re.compile(r"\n{3,}")
NON_WHITESPACE = re.compile(r"\s")
INVISIBLE_CHARACTERS = str.maketrans({"\u200b": None, "\ufeff": None})


class ContentValidationError(ValueError):
    """正文清洗后为空或未达到最小有效长度。"""


def clean_text(content: str) -> str:
    """规范正文空白和不可见字符，同时保留段落结构。"""

    normalized = unicodedata.normalize("NFC", html.unescape(content))
    normalized = normalized.translate(INVISIBLE_CHARACTERS).replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    return EXCESSIVE_NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def clean_and_validate_content(
    content: str,
    min_content_chars: int,
    *,
    content_label: str = "正文",
) -> str:
    """清洗正文，并以非空白字符数执行统一有效性校验。"""

    cleaned = clean_text(content)
    if not cleaned:
        raise ContentValidationError(f"{content_label}不能为空")

    effective_length = len(NON_WHITESPACE.sub("", cleaned))
    if effective_length < min_content_chars:
        raise ContentValidationError(
            f"{content_label}清洗后过短，至少需要 {min_content_chars} 个非空白字符"
        )
    return cleaned
