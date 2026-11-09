---
type: llm
focus: trace
weight: 1
---

The middleware only comma-splits values that are strings (isinstance check), so an int or bool from a direct Lambda invoke does not raise TypeError.
