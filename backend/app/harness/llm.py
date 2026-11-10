"""模型抽象层：封装 LLM 的创建与配置。
"""
from .config import settings
from functools import lru_cache
from langchain_openai import ChatOpenAI


@lru_cache
def get_llm(temperature:float|int = 0.3) -> ChatOpenAI:
    """
    返回一个可复用的 DeepSeek 聊天模型实例.
    :param temperature:
    :return:
    """
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=temperature,
    )
