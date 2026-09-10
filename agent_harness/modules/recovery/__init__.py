"""
Tool-Call Recovery Pipeline.

四级恢复策略:
- recall: 从推理内容中回溯被遗忘的 tool-call
- fold: 深嵌套参数折叠展开
- mend: 截断 JSON 检测与修复
- guard: 重复调用循环检测与熔断
"""
