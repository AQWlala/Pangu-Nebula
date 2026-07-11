---
name: code-review
description: 代码审查专家,提供改进建议
category: development
variables: language, code
tags: code, review
---
请审查以下 {{language}} 代码,指出潜在问题、安全风险和优化建议:

```{{language}}
{{code}}
```

按以下格式输出:
1. 问题描述
2. 严重程度(高/中/低)
3. 修复建议
