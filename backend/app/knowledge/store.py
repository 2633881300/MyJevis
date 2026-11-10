"""ChromaDB 向量存储：按知识库隔离，每个知识库一个 collection。

向量生命周期管理：
  chunk 的 id 用 f"{doc_id}::{chunk_index}" 构造 —— doc_id 来自 MySQL 的自增主键，
  全局唯一。这解决了三个问题：
    1. 同名文件重复上传：不同 doc_id → 不同 id，不会互相覆盖。
    2. 删除文档：可以按 doc_id 精确删掉该文档的所有 chunk。
    3. 上传失败回滚：已经写入的 chunk 可以按 doc_id 全部清理。
"""
from __future__ import annotations

from chromadb.errors import NotFoundError
from langchain_chroma import Chroma

from app.harness.config import settings
from app.knowledge.embedding import get_embedding_client
from app.knowledge.parser import Chunk


def _collection_name(kb_id: int) -> str:
    """知识库 id → collection 名。"""
    return f"kb_{kb_id}"


class VectorStore:
    """知识库的向量存储封装。"""

    def __init__(self) -> None:
        self._embedding = get_embedding_client()

    def _get_collection(self, kb_id: int) -> Chroma:
        """获取某个知识库对应的 Chroma collection（不存在则创建）。"""
        return Chroma(
            collection_name=_collection_name(kb_id),
            embedding_function=_EmbeddingAdapter(self._embedding),
            persist_directory=settings.chroma_dir,
        )

    def add_chunks(self, kb_id: int, doc_id: int, chunks: list[Chunk]) -> None:
        """把文本块入库到指定知识库（doc_id 用于构造全局唯一 id）。"""
        if not chunks:
            return
        store = self._get_collection(kb_id)
        texts = [c.text for c in chunks]

        metadatas = []
        for c in chunks:
            meta: dict = {
                "source": c.source,
                "chunk_index": c.chunk_index,
                "doc_id": doc_id,
                "file_type": c.file_type or "txt",
            }
            # Chroma 不接受 None 作为 metadata 值：只有 PDF 才写页码
            if c.page_number is not None:
                meta["page_number"] = c.page_number
            metadatas.append(meta)

        ids = [f"{doc_id}::{c.chunk_index}" for c in chunks]
        store.add_texts(texts=texts, metadatas=metadatas, ids=ids)

    def search(self, kb_id: int, query: str, k: int = 4) -> list[dict]:
        """在指定知识库中检索与 query 最相关的片段。"""
        store = self._get_collection(kb_id)
        docs = store.similarity_search(query, k=k)
        return [
            {
                "text": doc.page_content,
                "source": doc.metadata.get("source", "未知"),
                "chunk_index": doc.metadata.get("chunk_index", 0),
            }
            for doc in docs
        ]

    def search_with_score(self, kb_id: int, query: str, k: int = 4) -> list[dict]:
        """检索并返回相似度分数（ChromaDB 的 L2 距离，越小越相似）。"""
        store = self._get_collection(kb_id)
        docs_with_score = store.similarity_search_with_score(query, k=k)
        return [
            {
                "text": doc.page_content,
                "source": doc.metadata.get("source", "未知"),
                "chunk_index": doc.metadata.get("chunk_index", 0),
                "doc_id": doc.metadata.get("doc_id"),
                "file_type": doc.metadata.get("file_type", ""),
                "page_number": doc.metadata.get("page_number"),   # 仅 PDF 有
                "score": score,
            }
            for doc, score in docs_with_score
        ]

    def delete_document(self, kb_id: int, doc_id: int) -> int:
        """删除某文档在该知识库下的全部向量，返回删除条数。

        失败时**抛出异常**而不是静默返回 0 —— 调用方必须知道删除失败了，
        否则会出现「向量还在、SQL 记录已删」的不一致（内容仍可被检索到）。
        """
        store = self._get_collection(kb_id)
        before = store._collection.count()
        store._collection.delete(where={"doc_id": doc_id})
        after = store._collection.count()
        if after >= before:
            # 没删掉任何东西：可能 collection 不存在，也可能 where 没匹配到。
            # 后者意味着有残留，必须让上层知道。
            raise RuntimeError(
                f"向量删除未生效（kb={kb_id}, doc={doc_id}, {before}→{after}）"
            )
        return before - after

    def delete_collection(self, kb_id: int) -> bool:
        """删除整个知识库的向量集合。

        返回 False 只在「集合本来就不存在」这一种情况下出现（从未上传过文档）。
        真正的删除失败会**抛出异常**，让调用方停止后续的 MySQL 删除，
        避免出现「库里删了、向量还在」的残留。
        """
        try:
            self._get_collection(kb_id).delete_collection()
            return True
        except NotFoundError:
            return False


class _EmbeddingAdapter:
    """把 EmbeddingClient 适配成 langchain 期望的接口。"""

    def __init__(self, client) -> None:
        self._client = client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


# 全局单例
_store = VectorStore()


def get_vector_store() -> VectorStore:
    return _store
