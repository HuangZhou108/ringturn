# app/agent/atomic_tools/knowledge/search_knowledge.py
"""
知识检索工具（RAG）

agent 可自主调用它来检索音乐编曲知识库，
获取乐器选择、速度、移调、铃声编曲技巧等相关知识。
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.knowledge_base import retrieve_knowledge, format_knowledge


def search_knowledge(query: str) -> str:
    """检索音乐编曲知识库，返回相关的编曲知识。"""
    print(f"[RAG] search_knowledge 被调用，query={query}")
    docs = retrieve_knowledge(query, top_k=3)
    if not docs:
        return "未找到相关知识。"
    print(f"[RAG] 命中 {len(docs)} 篇知识: {[d['title'] for d in docs]}")
    return format_knowledge(docs)


class SearchKnowledgeInput(BaseModel):
    query: str = Field(description="要检索的知识主题/关键词，如「青春洋溢」「悠扬」「移调」「铃声」")


search_knowledge_tool = StructuredTool.from_function(
    func=search_knowledge,
    name="search_knowledge",
    description="检索音乐编曲知识库，返回相关的编曲知识（乐器选择、速度、移调、铃声技巧等）。当你不确定某类情绪/风格该怎么选乐器、定速度、移调时，可先调用它查询。",
    args_schema=SearchKnowledgeInput,
)
