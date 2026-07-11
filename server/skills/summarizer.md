---
name: summarizer
description: 长文摘要生成器
category: writing
variables: text, max_words
tags: summary, writing
---
请将以下文本压缩为不超过 {{max_words|default:"200"}} 字的摘要,保留核心观点:

{{text}}
