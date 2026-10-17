"""Topics: one set for every source, so the topic pills mean the same thing for Telegram and feeds.

An item keeps a topic its feed already gives it; otherwise the first configured pattern that
matches its title wins, then the first that matches its whole text (a title says what the story
is about; the body often mentions countries or markets in passing); otherwise the source's
default topic; otherwise 其他.
"""
import re
from shiguang.model import OTHER


def _first(text, topics):
    return next((name for name, pattern in topics.items() if re.search(pattern, text, re.I)), OTHER)


def classify(text, topics, title=''):
    found = _first(title, topics) if title else OTHER
    return found if found != OTHER else _first(text, topics)


def assign(items, topics, default=''):
    """Fill item.category (filtering) and item.topic (the label on the card) in place."""
    for item in items:
        if not item.category:
            found = classify(item.title + '\n' + item.body, topics, item.title)
            item.category = default if found == OTHER and default else found
        item.topic = '' if item.category == OTHER else item.category
    return items
