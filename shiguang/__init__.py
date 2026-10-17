"""拾光热点: every channel becomes one kind of item, and five pages take what they need.

Layers, in the order a build runs them:
  ingest/  collect content: Telegram into tg.db, inbox feeds from disk
  model.py the shapes every layer shares: Item, and the helpers that turn rows and feeds into it
  enrich/  text cleanup, topics, the live ranking, home ordering
  site/    pages, components, icons, light; staged publication and the privacy check
"""
