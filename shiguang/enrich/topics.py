"""Topics: the first configured topic whose pattern matches the text, else 综合."""
import re

FALLBACK = '综合'


def classify(text, topics):
    return next((name for name, pattern in topics.items() if re.search(pattern, text, re.I)), FALLBACK)
