"""Topics: one set for every source, so the topic pills mean the same thing for Telegram and feeds.

An item keeps a topic its feed already gives it; otherwise the first configured pattern that
matches its text wins; otherwise the source's default topic; otherwise 其他.
"""
import re
from shiguang.model import OTHER


def classify(text, topics):
    return next((name for name, pattern in topics.items() if re.search(pattern, text, re.I)), OTHER)


def assign(items, topics, default=''):
    """Fill item.category (filtering) and item.topic (the label on the card) in place."""
    for item in items:
        if not item.category:
            found = classify(item.title + '\n' + item.body, topics)
            item.category = default if found == OTHER and default else found
        item.topic = '' if item.category == OTHER else item.category
    return items
