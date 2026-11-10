"""Embedding 封装: 把文本转成向量"""

from __future__ import annotations

from openai import OpenAI

from app.harness.config import settings

class EmbeddingClient:
    """向量化客户端,封装硅基流动的 embedding 接口"""
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )
        self._model = settings.embedding_model

    def embed_texts(self,texts: list[str]) -> list[list[float]]:
        """将一批文本转成向量,返回与输入等长的向量列表"""
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model,input=texts)
        data = sorted(resp.data,key=lambda d:d.index)
        return [d.embedding for d in data]

    def embed_query(self,text: str) -> list[float]:
        return self.embed_texts([text])[0]

_embedding_client = EmbeddingClient()

def get_embedding_client() -> EmbeddingClient:
    return _embedding_client