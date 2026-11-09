---
type: llm
focus: trace
weight: 1
---

The SQLAlchemy code uses select(...) without a list, and rows are unpacked via .mappings() or an equivalent; the test seed no longer relies on engine.connect() autocommit.
