"""工具注册机制：定义工具抽象与 ToolRegistry。

    任何业务能力,只要写一个普通函数,通过 register_function 包装成工具并注册,就能被 agent 调用
"""

# 延迟类型注解求值，避免前向引用报错
from __future__ import annotations
from typing import Any, Callable
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

class ToolRegistry:
    """工具注册表: 管理所有可供 agent 调用的工具"""
    def __init__(self)->None:
        self._tools: dict[str,BaseTool] = {}

    def register(self,tool:BaseTool)->BaseTool:
        """注册一个工具,按工具名去重,同名则报错"""
        if tool.name in self._tools:
            raise ValueError(f"工具名重复:{tool.name}")
        self._tools[tool.name] = tool
        return tool

    def register_function(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        args_schema: type[BaseModel] | None = None,
        ) -> BaseTool:
        """"把一个普通 Python 函数包装成工具并注册."""
        tool = StructuredTool.from_function(
            func=func,
            name=name or func.__name__,
            description=description or func.__doc__ or "",
            args_schema=args_schema,
        )
        return self.register(tool)

    def get_all(self) -> list[BaseTool]:
        """返回所有已注册工具,供绑定到模型"""
        return list(self._tools.values())

    def get(self,name: str) -> BaseTool | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)






