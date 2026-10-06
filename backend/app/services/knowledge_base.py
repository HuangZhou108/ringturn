"""Persistent music-arrangement knowledge base with hybrid retrieval."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import KnowledgeDocument
from app.services.hybrid_retrieval import hybrid_scores


BUILTIN_DOCUMENTS = [
    ("builtin-upbeat", "青春洋溢/欢快风格的编曲建议", "明亮清脆的乐器：Music Box、Glockenspiel、Bright Acoustic Piano、Electric Piano、Marimba、Vibraphone。速度偏快，约为检测 BPM 的 110%~120%。用高音区、轻快节奏营造青春活力。", ["欢快", "明亮", "活力"]),
    ("builtin-lyrical", "悠扬/抒情风格的编曲建议", "柔美乐器：Violin、Acoustic Grand Piano、Celesta、Orchestral Harp、Warm Pad。速度偏慢（80~96 BPM）。用长音、延音营造悠扬感，避免密集短音符。", ["抒情", "舒缓", "安静"]),
    ("builtin-sad", "忧伤/伤感风格的编曲建议", "温暖低沉乐器：Cello、Clarinet、String Ensemble、Acoustic Grand Piano。速度偏慢。用中低音区、连音表达情感。", ["忧伤", "伤感", "低沉"]),
    ("builtin-epic", "激昂/史诗风格的编曲建议", "Brass Section、String Ensemble、Overdriven Guitar。速度中快。用强力度、厚和声营造气势。", ["激昂", "史诗", "戏剧性"]),
    ("builtin-ringtone", "手机铃声编曲技巧", "截取副歌或高潮最有记忆点的乐句；开头快速进入主题；结尾自然收束或淡出；外放清晰不刺耳；时长通常为 30~60 秒。", ["铃声", "剪辑", "循环"]),
    ("builtin-transpose", "移调与音域技巧", "旋律整体偏低可上移八度（+12），偏高可下移八度（-12）。目标是让旋律落在目标乐器舒适音域，通常限制在 -12~+12 半音。", ["移调", "音域"]),
    ("builtin-legato", "音符连贯性处理", "用延音 sustain 和连奏 legato 让音符衔接连贯。避免大量短碎音符，可合并相邻同音高音符。", ["连奏", "延音", "连贯"]),
]

# Compatibility for existing imports.
DOCUMENTS = [
    {"title": title, "content": content, "tags": tags}
    for _, title, content, tags in BUILTIN_DOCUMENTS
]


def ensure_builtin_knowledge(db: Session | None = None) -> int:
    """Idempotently seed built-in documents into the persistent store."""
    owns_session = db is None
    db = db or SessionLocal()
    created = 0
    try:
        for key, title, content, tags in BUILTIN_DOCUMENTS:
            if db.query(KnowledgeDocument.id).filter(
                KnowledgeDocument.document_key == key
            ).first():
                continue
            try:
                with db.begin_nested():
                    db.add(KnowledgeDocument(
                        document_key=key,
                        title=title,
                        content=content,
                        tags=tags,
                        source="builtin",
                    ))
                    db.flush()
                created += 1
            except IntegrityError:
                # Another worker may have seeded the same document concurrently.
                pass
        db.commit()
        return created
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def make_document_key(title: str, content: str, profile_id: int | None = None) -> str:
    digest = hashlib.sha256(f"{profile_id}:{title}:{content}".encode("utf-8")).hexdigest()[:24]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "document"
    return f"custom-{slug}-{digest}"


def retrieve_knowledge(
    query: str,
    top_k: int = 3,
    *,
    profile_id: int | None = None,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    """Retrieve global and profile-scoped documents with hybrid ranking."""
    owns_session = db is None
    db = db or SessionLocal()
    try:
        ensure_builtin_knowledge(db)
        candidates = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.enabled == 1,
            (KnowledgeDocument.profile_id.is_(None))
            | (KnowledgeDocument.profile_id == profile_id),
        ).all()
        texts = [f"{item.title} {' '.join(item.tags or [])} {item.content}" for item in candidates]
        scores = hybrid_scores(query, texts)
        ranked = sorted(
            zip(scores, candidates),
            key=lambda pair: (pair[0], pair[1].profile_id is not None, pair[1].updated_at),
            reverse=True,
        )
        results = []
        for score, item in ranked:
            if score <= 0 and query.strip():
                continue
            results.append({
                "id": item.id,
                "document_key": item.document_key,
                "profile_id": item.profile_id,
                "title": item.title,
                "content": item.content,
                "tags": list(item.tags or []),
                "source": item.source,
                "score": score,
            })
            if len(results) >= max(1, min(top_k, 20)):
                break
        return results
    finally:
        if owns_session:
            db.close()


def format_knowledge(docs: list[dict]) -> str:
    """Format retrieval results with source and relevance for prompt injection."""
    if not docs:
        return ""
    return "\n".join(
        f"【{doc['title']}｜来源:{doc.get('source', 'unknown')}｜相关度:{doc.get('score', 0):.3f}】{doc['content']}"
        for doc in docs
    )
