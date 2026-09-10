"""pytest 全局夹具 —— 把框架运行状态隔离到临时目录。

ModelRouter 与 FeedbackEngine 默认把状态（学习到的路由模式、反馈权重、
收敛历史、动态阈值）写进包内的 feedback/。如果不隔离会有两个后果：

1. 跑一遍测试就污染下一次运行 —— 第二遍会命中上一遍留下的学习模式，
   路由短路到 learned_regex 分支，导致断言失败（"跑一次绿、跑两次红"）。
2. 源码树里会留下运行时数据，可能混入使用者真实输入，不该进版本库。

这里在收集任何测试模块之前把 AGENT_HARNESS_STATE_DIR 指向临时目录，
让整套测试对工作区零写入。若外部已显式设置该变量，则尊重外部设置。
"""

import os
import sys
import tempfile
from pathlib import Path

# 保证 `import agent_harness` 可用（直接 python -m pytest tests/ 时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault(
    "AGENT_HARNESS_STATE_DIR",
    tempfile.mkdtemp(prefix="agent_harness_test_state_"),
)
