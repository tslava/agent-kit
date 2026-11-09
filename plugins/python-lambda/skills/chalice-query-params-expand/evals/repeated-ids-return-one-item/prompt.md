---
tags: [python-lambda]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our /items endpoint returns only one item when the frontend calls /items?ids=1&ids=2&ids=3, but /items?ids=1,2,3 works. Other services also call this Lambda directly. Fix it.

Input files: app.py, test_app.py
