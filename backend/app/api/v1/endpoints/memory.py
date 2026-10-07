"""Management and retrieval APIs for RAG documents and long-term memory."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import KnowledgeDocument, LongTermMemory, Profile
from app.schemas.memory import KnowledgeDocumentCreate, MemoryCreate, MemoryUpdate
from app.services.knowledge_base import make_document_key, retrieve_knowledge
from app.services.memory import MEMORY_KINDS, remember, retrieve_memories

router = APIRouter(tags=["memory"])


def _require_profile(db: Session, profile_id: int) -> None:
    if not db.query(Profile.id).filter(Profile.id == profile_id).first():
        raise HTTPException(status_code=404, detail=f"Profile 不存在: {profile_id}")


def _serialize_memory(memory: LongTermMemory) -> dict:
    return {
        "id": memory.id,
        "profile_id": memory.profile_id,
        "kind": memory.kind,
        "content": memory.content,
        "source_task_id": memory.source_task_id,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "pinned": bool(memory.pinned),
        "metadata": dict(memory.memory_metadata or {}),
        "access_count": memory.access_count,
        "last_accessed_at": memory.last_accessed_at,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


@router.post("/profiles/{profile_id}/memories")
def create_memory(profile_id: int, request: MemoryCreate, db: Session = Depends(get_db)):
    _require_profile(db, profile_id)
    memory = remember(
        profile_id,
        request.content,
        kind=request.kind,
        importance=request.importance,
        confidence=request.confidence,
        pinned=request.pinned,
        metadata=request.metadata,
        db=db,
    )
    return {"code": 200, "data": _serialize_memory(memory), "message": "长期记忆已保存。"}


@router.get("/profiles/{profile_id}/memories")
def list_memories(
    profile_id: int,
    query: str = "",
    kind: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _require_profile(db, profile_id)
    if kind and kind not in MEMORY_KINDS:
        raise HTTPException(status_code=422, detail=f"不支持的记忆类型: {kind}")
    if query.strip():
        items = retrieve_memories(
            profile_id,
            query,
            top_k=limit,
            kinds={kind} if kind else None,
            db=db,
        )
        return {"code": 200, "data": items, "message": "记忆检索成功。"}
    statement = db.query(LongTermMemory).filter(LongTermMemory.profile_id == profile_id)
    if kind:
        statement = statement.filter(LongTermMemory.kind == kind)
    memories = statement.order_by(
        LongTermMemory.pinned.desc(),
        LongTermMemory.importance.desc(),
        LongTermMemory.updated_at.desc(),
    ).limit(limit).all()
    return {"code": 200, "data": [_serialize_memory(item) for item in memories], "message": "记忆列表获取成功。"}


@router.patch("/profiles/{profile_id}/memories/{memory_id}")
def update_memory(
    profile_id: int,
    memory_id: str,
    request: MemoryUpdate,
    db: Session = Depends(get_db),
):
    memory = db.query(LongTermMemory).filter(
        LongTermMemory.id == memory_id,
        LongTermMemory.profile_id == profile_id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="长期记忆不存在")
    updates = request.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(memory, key, int(value) if key == "pinned" else value)
    memory.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(memory)
    return {"code": 200, "data": _serialize_memory(memory), "message": "长期记忆已更新。"}


@router.delete("/profiles/{profile_id}/memories/{memory_id}")
def delete_memory(profile_id: int, memory_id: str, db: Session = Depends(get_db)):
    deleted = db.query(LongTermMemory).filter(
        LongTermMemory.id == memory_id,
        LongTermMemory.profile_id == profile_id,
    ).delete(synchronize_session=False)
    if not deleted:
        raise HTTPException(status_code=404, detail="长期记忆不存在")
    db.commit()
    return {"code": 200, "data": {"memory_id": memory_id}, "message": "长期记忆已删除。"}


@router.get("/knowledge/search")
def search_knowledge(
    query: str = Query(min_length=1, max_length=1000),
    profile_id: int | None = None,
    top_k: int = Query(default=4, ge=1, le=20),
    db: Session = Depends(get_db),
):
    if profile_id is not None:
        _require_profile(db, profile_id)
    results = retrieve_knowledge(query, top_k, profile_id=profile_id, db=db)
    return {"code": 200, "data": results, "message": "知识检索成功。"}


@router.get("/knowledge/documents")
def list_knowledge_documents(
    profile_id: int | None = None,
    include_disabled: bool = False,
    db: Session = Depends(get_db),
):
    statement = db.query(KnowledgeDocument).filter(
        (KnowledgeDocument.profile_id.is_(None))
        | (KnowledgeDocument.profile_id == profile_id)
    )
    if not include_disabled:
        statement = statement.filter(KnowledgeDocument.enabled == 1)
    documents = statement.order_by(KnowledgeDocument.profile_id, KnowledgeDocument.id).all()
    return {"code": 200, "data": [
        {
            "id": item.id,
            "document_key": item.document_key,
            "profile_id": item.profile_id,
            "title": item.title,
            "content": item.content,
            "tags": item.tags or [],
            "source": item.source,
            "enabled": bool(item.enabled),
            "updated_at": item.updated_at,
        }
        for item in documents
    ], "message": "知识文档列表获取成功。"}


@router.post("/knowledge/documents")
def create_knowledge_document(
    request: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
):
    if request.profile_id is not None:
        _require_profile(db, request.profile_id)
    tags = list(dict.fromkeys(tag.strip()[:64] for tag in request.tags if tag.strip()))
    key = make_document_key(request.title, request.content, request.profile_id)
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_key == key).first()
    if not document:
        document = KnowledgeDocument(
            document_key=key,
            profile_id=request.profile_id,
            title=request.title.strip(),
            content=request.content.strip(),
            tags=tags,
            source=request.source.strip(),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    return {"code": 200, "data": {"id": document.id, "document_key": document.document_key}, "message": "知识文档已保存。"}


@router.delete("/knowledge/documents/{document_id}")
def delete_knowledge_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    if document.source == "builtin":
        raise HTTPException(status_code=409, detail="内置知识不能删除")
    db.delete(document)
    db.commit()
    return {"code": 200, "data": {"document_id": document_id}, "message": "知识文档已删除。"}
