import html
import re
import unicodedata


HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")
EXCESSIVE_NEWLINES = re.compile(r"\n{3,}")
INVISIBLE_CHARACTERS = str.maketrans({"\u200b": None, "\ufeff": None})


def clean_text(content: str) -> str:
    """规范正文空白和不可见字符，同时保留段落结构。"""

    normalized = unicodedata.normalize("NFC", html.unescape(content))
    normalized = normalized.translate(INVISIBLE_CHARACTERS).replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    return EXCESSIVE_NEWLINES.sub("\n\n", "\n".join(lines)).strip()
