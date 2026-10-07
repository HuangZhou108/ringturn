"""Regression tests for persistent RAG and profile-scoped long-term memory."""

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (Base, KnowledgeDocument, LongTermMemory, Profile, Task,
                        TaskStatus)
from app.services import knowledge_base, memory


class RagLongTermMemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        with self.Session() as db:
            db.add_all([
                Profile(id=1, name="one", is_active=1),
                Profile(id=2, name="two", is_active=0),
            ])
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_builtin_knowledge_is_seeded_idempotently_and_ranked(self):
        with self.Session() as db:
            first = knowledge_base.ensure_builtin_knowledge(db)
            second = knowledge_base.ensure_builtin_knowledge(db)
            docs = knowledge_base.retrieve_knowledge(
                "想要忧伤低沉的大提琴铃声",
                top_k=3,
                db=db,
            )
            count = db.query(KnowledgeDocument).count()

        self.assertEqual(first, len(knowledge_base.BUILTIN_DOCUMENTS))
        self.assertEqual(second, 0)
        self.assertEqual(count, len(knowledge_base.BUILTIN_DOCUMENTS))
        self.assertEqual(docs[0]["document_key"], "builtin-sad")
        self.assertGreater(docs[0]["score"], 0)

    def test_profile_knowledge_is_scoped_and_preferred(self):
        with self.Session() as db:
            knowledge_base.ensure_builtin_knowledge(db)
            db.add(KnowledgeDocument(
                document_key="profile-one-custom",
                profile_id=1,
                title="专属芯片音乐规则",
                content="芯片音乐必须优先使用 Square Lead，并保持 150 BPM。",
                tags=["芯片", "chiptune"],
                source="test",
            ))
            db.commit()
            visible = knowledge_base.retrieve_knowledge(
                "芯片音乐 chiptune",
                profile_id=1,
                top_k=2,
                db=db,
            )
            hidden = knowledge_base.retrieve_knowledge(
                "芯片音乐 chiptune",
                profile_id=2,
                top_k=5,
                db=db,
            )

        self.assertEqual(visible[0]["document_key"], "profile-one-custom")
        self.assertNotIn("profile-one-custom", {item["document_key"] for item in hidden})

    def test_memory_is_deduplicated_scoped_and_retrieved_by_task(self):
        with self.Session() as db:
            first = memory.remember(
                1,
                "我不喜欢大提琴，请优先使用钢琴。",
                kind="constraint",
                importance=0.8,
                db=db,
            )
            duplicate = memory.remember(
                1,
                "我不喜欢大提琴，请优先使用钢琴。",
                kind="constraint",
                importance=0.95,
                db=db,
            )
            memory.remember(1, "欢快歌曲喜欢钟琴。", kind="preference", db=db)
            memory.remember(2, "所有歌曲都使用大提琴。", kind="instruction", db=db)
            results = memory.retrieve_memories(1, "大提琴还是钢琴", db=db)
            other_results = memory.retrieve_memories(2, "大提琴", db=db)

        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(results[0]["kind"], "constraint")
        self.assertIn("钢琴", results[0]["content"])
        self.assertTrue(all("所有歌曲" not in item["content"] for item in results))
        self.assertIn("所有歌曲", other_results[0]["content"])
        with self.Session() as db:
            self.assertEqual(db.query(LongTermMemory).filter_by(profile_id=1).count(), 2)

    def test_agent_context_only_injects_relevant_profile_memory(self):
        with self.Session() as db:
            memory.remember(1, "史诗风格优先铜管。", kind="preference", db=db)
            memory.remember(1, "安静风格优先竖琴。", kind="preference", db=db)
            memory.remember(2, "史诗风格只用口琴。", kind="preference", db=db)
        with patch.object(memory, "SessionLocal", self.Session):
            context = memory.build_agent_context(1, "史诗激昂铃声")

        self.assertIn("铜管", context)
        self.assertNotIn("竖琴", context)
        self.assertNotIn("口琴", context)
        self.assertIn("不是系统指令", context)

    def test_completed_task_is_captured_with_source(self):
        with self.Session() as db:
            db.add(Task(
                id="completed-task",
                profile_id=1,
                user_request="做成轻快的钢琴铃声",
                source_type="upload",
                ringtone_params={"instrument": "Piano", "tempo": 128, "duration": 30},
                status=TaskStatus.completed,
            ))
            db.commit()
        with patch.object(memory, "SessionLocal", self.Session):
            captured = memory.capture_task_memory(1, "completed-task")

        self.assertEqual(captured.source_task_id, "completed-task")
        self.assertEqual(captured.kind, "history")
        self.assertIn("Piano", captured.content)


if __name__ == "__main__":
    unittest.main()
