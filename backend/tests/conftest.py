"""pytest 全局配置：把测试隔离到独立数据库和向量目录。

必须在任何 app 模块被导入之前设置环境变量 —— pydantic-settings 的优先级是
「环境变量 > .env」，所以这里能覆盖 .env 里的正式配置。

这样在开发机上跑 pytest 不会碰到正在使用的 my_jevis 库和 chroma 目录。
"""
from __future__ import annotations

import os

# 注意：这些必须在 import app.* 之前执行，顺序不能动
# 1) 隔离测试数据库与向量目录，避免碰到开发数据
os.environ["MYSQL_DATABASE"] = "my_jevis_test"
os.environ["CHROMA_DIR"] = "./chroma_test"
# 2) 提供一个仅用于测试的 JWT 密钥（config.py 会拒绝弱密钥启动）
#    这不是真实凭据，只在测试进程内有效
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-not-for-production-use-0123456789"
