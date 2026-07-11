---
name: json-formatter
description: JSON 格式化工具
category: utility
type: python
input_schema: '{"type":"object","properties":{"json_str":{"type":"string"}},"required":["json_str"]}'
output_schema: '{"type":"object","properties":{"formatted":{"type":"string"},"valid":{"type":"boolean"}}}'
tags: json, format
---
import json

data = json.loads(INPUT['json_str'])
formatted = json.dumps(data, indent=2, ensure_ascii=False)
OUTPUT = {"formatted": formatted, "valid": True}
