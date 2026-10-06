"""
Agent执行器

协调 LangGraph 图执行，管理状态初始化、计划生成和结果同步
"""

import asyncio
import time
from asyncio import Task as AsyncioTask
from datetime import datetime
from typing import Optional

from app.agent.graph import get_agent_graph
from app.agent.resilience import ExecutionDeadlineExceeded
from app.agent.state import AgentState
from app.agent.thinking_utils import record_thought
from app.agent.trace import (build_execution_error, create_trace_event,
                             merge_trace_events, persist_trace_event,
                             redact_text, reset_execution_context,
                             set_execution_context)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (Conversation, ConversationMessage, ConversationStatus,
                        MessageRole)
from app.models import Task as TaskModel
from app.models import TaskStatus
from app.services.llm_service import llm_service
from sqlalchemy.orm import Session

settings = get_settings()


class RingtoneParams:
    def __init__(self, task: TaskModel):
        params = task.ringtone_params or {}
        self.instrument = params.get("instrument", "Acoustic Piano")
        self.duration = params.get("duration", 30)
        self.tempo = params.get("tempo", 120)
        self.filename = params.get("filename", "ringtone")
        self.file_id = task.source_value
        self.max_retries = params.get("max_retries", 1)  # 用户可配置重试次数，默认允许重试 1 次
        self.raw_params = params

class AgentExecutor:
    def __init__(
        self,
        task_id: str,
        db: Session = None,
        conversation_id: str = None,
        recovering: bool = False,
    ):
        self.task_id = task_id
        self.db = db if db is not None else SessionLocal(expire_on_commit=False)
        self._owns_db = db is None  # 标记是否自己创建的会话
        self.conversation_id = conversation_id
        self._active_task: Optional[AsyncioTask] = None
        self._execution_task: Optional[AsyncioTask] = None
        self._cancel_event = asyncio.Event()   # 用于通知内部协程取消
        self._suspend_reason: str | None = None
        self._recovering = recovering
        self._subprocesses = []   # 保存子进程对象
        self._pipeline_timeout_seconds = max(
            0.001,
            float(settings.AGENT_PIPELINE_TIMEOUT_SECONDS),
        )

        # 获取任务
        self.task = self.db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not self.task:
            raise ValueError(f"任务不存在: {task_id}")

        # 如果没有传入 conversation_id，尝试从数据库中查找
        if not self.conversation_id:
            user_message = self.db.query(ConversationMessage).filter(
                ConversationMessage.task_id == task_id,
                ConversationMessage.role == MessageRole.user
            ).first()
            if user_message:
                self.conversation_id = user_message.conversation_id

        # 解析铃声参数
        self.ringtone_params = RingtoneParams(self.task)
        self.state = self._init_state()
        self.graph = None   # 延迟加载

        # 查找该任务对应的 assistant 消息（应该存在）
        self.assistant_message = None
        if self.conversation_id:
            self.assistant_message = self.db.query(ConversationMessage).filter(
                ConversationMessage.task_id == task_id,
                ConversationMessage.role == MessageRole.assistant
            ).first()

    def _init_state(self) -> AgentState:
        """初始化 Agent 状态"""
        state = {
            "task_id": self.task.id,
            "profile_id": self.task.profile_id,
            "user_request": self.task.user_request,
            "source_type": self.task.source_type,
            "source_value": self.task.source_value,
            "instrument": self.ringtone_params.instrument,
            "duration": self.ringtone_params.duration,
            "tempo": self.ringtone_params.tempo,
            "filename": self.ringtone_params.filename,
            "file_id": self.ringtone_params.file_id,
            "max_retries": self.ringtone_params.max_retries,
            "audio_path": None,
            "demucs_separated": False,
            "vocals_path": None,
            "accompaniment_path": None,
            "analysis_result": None,
            "melody_data": None,
            "melody_source_path": None,
            "harmony_source_path": None,
            "source_for_melody": None,
            "melody_extractor": None,
            "melody_candidates": {},
            "melody_candidate_summary": {},
            "selected_melody_extractor": None,
            "midi_path": None,
            "arrangement_params": None,
            "arranged_midi_path": None,
            "final_audio_path": None,
            "final_audio_url": None,
            "audio_duration": None,
            "current_step": None,
            "current_step_index": 0,
            "plan": [],
            "step_results": {},
            "feedback_history": [],
            "reflection": None,
            "needs_revision": False,
            "error": None,
            "retry_count": 0,
            "thread_id": self.task.id,
            "execution_trace": [],
            "execution_error": None,
            "created_at": self.task.created_at,
            "updated_at": datetime.utcnow(),
        }

        # 反馈、人工恢复和崩溃恢复都复用已持久化的安全中间产物。
        if self.task.intermediate_data and (
            self.task.parent_task_id or self.task.resume_from_node or self._recovering
        ):
            inter = self.task.intermediate_data
            print(f"[DEBUG] intermediate_data: {inter}")
            state.update({
                "audio_path": inter.get("audio_path"),
                "demucs_separated": inter.get("demucs_separated", False),
                "vocals_path": inter.get("vocals_path"),
                "accompaniment_path": inter.get("accompaniment_path"),
                "analysis_result": inter.get("analysis_result"),
                "melody_data": inter.get("melody_data"),
                "melody_source_path": inter.get("melody_source_path"),
                "harmony_source_path": inter.get("harmony_source_path"),
                "source_for_melody": inter.get("source_for_melody"),
                "melody_extractor": inter.get("melody_extractor"),
                "melody_candidate_summary": inter.get("melody_candidate_summary", {}),
                "selected_melody_extractor": inter.get("selected_melody_extractor"),
                "midi_path": inter.get("midi_path"),
                "arranged_midi_path": inter.get("arranged_midi_path"),
                "tempo": inter.get("tempo", 120),
                "instrument": inter.get("instrument", "Acoustic Piano"),
            })
            # Feedback tasks copy audio intermediates, not the parent's diagnostics.
            state["execution_trace"] = [
                event
                for event in inter.get("execution_trace", [])
                if isinstance(event, dict) and event.get("task_id") == self.task.id
            ]
            state["execution_error"] = None
            # 用用户反馈中新指定的参数覆盖父任务的旧值
            if self.ringtone_params.instrument:
                state["instrument"] = self.ringtone_params.instrument
            if self.ringtone_params.tempo:
                state["tempo"] = self.ringtone_params.tempo
            if self.ringtone_params.duration:
                state["duration"] = self.ringtone_params.duration
            if self.ringtone_params.filename:
                state["filename"] = self.ringtone_params.filename

        return state

    async def _plan(self) -> None:
        """规划阶段：生成执行计划（仅用于展示，不影响图路由）"""
        from app.services.llm_service import llm_service

        user_request = self.state["user_request"]

        # 解析自然语言中的时长（如"60s左右"/"1分钟"），覆盖 UI 默认值
        try:
            nl_duration = await llm_service.extract_duration(user_request)
            if nl_duration and nl_duration > 0:
                self.state["duration"] = int(nl_duration)
                self._add_thinking_step("规划", f"从自然语言识别到目标时长: {int(nl_duration)} 秒")
        except Exception as e:
            print(f"[PLAN] extract_duration failed: {type(e).__name__}")

        ringtone_params = self.ringtone_params.raw_params
        param_desc = ""
        if ringtone_params:
            param_desc = "\n用户指定了以下参数：\n"
            for k, v in ringtone_params.items():
                param_desc += f"- {k}: {v}\n"

        full_prompt = f"{user_request}\n{param_desc}\n请根据用户需求和参数约束生成执行计划。"
        self._add_thinking_step("规划", f"分析用户需求: {user_request[:50]}...")
        plan = await llm_service.generate_plan(full_prompt)

        # 生成自然语言思考（仅展示性初步思路，不涉及具体乐器/速度等最终决策）
        thoughts_prompt = (
            f"用户想要将一首歌曲改编为手机铃声。需求：{user_request}。"
            f"目标时长：{self.state['duration']} 秒。"
            "请用简短的自然语言描述你的整体改编思路（比如截取哪个部分、营造什么情绪氛围）。"
            "注意：这只是初步规划，具体的乐器、速度、移调会在音频分析后由系统自动决定，"
            "请不要断言具体的乐器名或 BPM 数值。"
        )
        try:
            thinking_msg = await llm_service.chat(
                [{"role": "user", "content": thoughts_prompt}],
                temperature=0.7,
                max_tokens=200,
            )
            self._add_thinking_step("规划", thinking_msg)
            self.state["plan_description"] = thinking_msg
        except Exception:
            self._add_thinking_step("规划", "根据用户需求自动生成改编计划。")

        normalized_plan = []
        for item in plan:
            if isinstance(item, dict) and "step" in item:
                normalized_plan.append(item["step"])
            else:
                normalized_plan.append(item)
        self.state["plan"] = normalized_plan
        self.task.plan = normalized_plan
        self.db.commit()

    def bind_execution_task(self, task: AsyncioTask) -> None:
        """Bind the outer runner so cancellation also interrupts planning."""
        self._execution_task = task

    def _cancellation_requested(self) -> bool:
        """Check both process-local and persisted cancellation signals."""
        if self._cancel_event.is_set():
            return True
        # Avoid flushing partially assembled results while polling a status that
        # may have been changed by the cancellation endpoint in another session.
        with self.db.no_autoflush:
            persisted_status = (
                self.db.query(TaskModel.status)
                .filter(TaskModel.id == self.task_id)
                .scalar()
            )
        return persisted_status == TaskStatus.cancelled

    async def _finalize_cancellation(self, execute_started_at: float) -> bool:
        """Discard partial writes and persist one cancellation outcome."""
        self.db.rollback()
        self.task.error_message = "任务已被用户取消"
        if not await self._update_task_status(TaskStatus.cancelled):
            return False

        cancelled_error = build_execution_error(
            asyncio.CancelledError("Task cancelled"),
            scope="task",
            component="agent_execution",
        )
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="task",
                name="agent_execution",
                status="cancelled",
                duration_ms=(time.perf_counter() - execute_started_at) * 1000,
                error=cancelled_error,
            ),
        )
        if self.assistant_message:
            self.assistant_message.content = "任务已取消"
        self.db.commit()
        return True

    async def _finalize_suspension(self, execute_started_at: float) -> None:
        """Leave the persisted task resumable after shutdown or human pause."""
        self.db.rollback()
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="resilience",
                name="runtime_interruption",
                status="suspended",
                duration_ms=(time.perf_counter() - execute_started_at) * 1000,
                details={"reason": self._suspend_reason or "runtime_shutdown"},
            ),
        )

    async def execute(self) -> dict:
        """执行任务：调用 LangGraph 图"""
        execute_started_at = time.perf_counter()
        pipeline_deadline = execute_started_at + self._pipeline_timeout_seconds
        execution_context_token = set_execution_context(
            self.task_id,
            "agent_execution",
        )
        memory_context_token = None
        memory_profile_token = None
        try:
            self.task.thread_id = self.task_id
            started_event = create_trace_event(
                task_id=self.task_id,
                kind="task",
                name="agent_execution",
                status="running",
                details={
                    "pipeline_timeout_seconds": self._pipeline_timeout_seconds,
                },
            )
            self.state["execution_trace"] = merge_trace_events(
                self.state.get("execution_trace"),
                [started_event],
            )
            persist_trace_event(self.task_id, started_event)
            # 注入 Agent 记忆（全局偏好 + 历史画像），供本次任务所有 LLM 调用使用
            from app.services.memory import (build_agent_context, set_agent_context,
                                             set_agent_profile_id)

            ctx = None
            memory_metadata = {"memory_count": 0}
            memory_status = "succeeded"
            try:
                memory_query = " ".join(
                    filter(
                        None,
                        [
                            self.state.get("user_request", ""),
                            str(self.state.get("instrument", "")),
                            str(self.state.get("tempo", "")),
                        ],
                    )
                )
                ctx, memory_metadata = await asyncio.to_thread(
                    build_agent_context,
                    self.state.get("profile_id"),
                    memory_query,
                    True,
                )
            except Exception as e:
                memory_status = "failed"
                print(f"[MEMORY] build_agent_context failed: {type(e).__name__}")
            memory_context_token = set_agent_context(ctx)
            memory_profile_token = set_agent_profile_id(self.state.get("profile_id"))
            memory_event = create_trace_event(
                task_id=self.task_id,
                kind="memory",
                name="context_retrieval",
                status=memory_status,
                details={
                    **memory_metadata,
                    "context_injected": bool(ctx),
                },
            )
            self.state["execution_trace"] = merge_trace_events(
                self.state.get("execution_trace"),
                [memory_event],
            )
            persist_trace_event(self.task_id, memory_event)

            # 检查是否已取消
            if self._cancellation_requested():
                raise asyncio.CancelledError()
            
            # 将反馈指定的起始节点注入 state
            if self.task.resume_from_node:
                self.state["resume_from_node"] = self.task.resume_from_node
                print(f"[AGENT] Will resume from node: {self.task.resume_from_node}")

            recovering_graph = self._recovering and self.task.status == TaskStatus.executing
            if not recovering_graph:
                if not await self._update_task_status(TaskStatus.planning):
                    raise asyncio.CancelledError()
                await self._await_before_deadline(
                    self._plan(),
                    deadline=pipeline_deadline,
                    component="planning",
                )
            else:
                self._add_thinking_step("恢复", "检测到未完成执行，正在从持久化检查点恢复。")

            if self._cancellation_requested():
                raise asyncio.CancelledError()

            if not await self._update_task_status(TaskStatus.executing):
                raise asyncio.CancelledError()
            # 异步获取图实例
            self.graph = await get_agent_graph()
            config = {"configurable": {"thread_id": self.task_id}}
            # final_state = await self.graph.ainvoke(self.state, config=config)

            graph_input = self.state
            checkpoint_state = None
            if recovering_graph or self.task.resume_from_node:
                checkpoint_state = await self.graph.aget_state(config)
                if checkpoint_state and checkpoint_state.values:
                    self.state.update(dict(checkpoint_state.values))
                    # Explicit user input starts from the requested node but uses
                    # the latest checkpointed artifacts and the newly validated
                    # ringtone parameters.
                    if self.task.resume_from_node:
                        self.state.update(
                            {
                                "resume_from_node": self.task.resume_from_node,
                                "instrument": self.ringtone_params.instrument,
                                "tempo": self.ringtone_params.tempo,
                                "duration": self.ringtone_params.duration,
                                "filename": self.ringtone_params.filename,
                            }
                        )
                        graph_input = self.state
                    elif checkpoint_state.next:
                        graph_input = None

            if (
                recovering_graph
                and checkpoint_state
                and checkpoint_state.values
                and not checkpoint_state.next
            ):
                final_state = dict(checkpoint_state.values)
            else:
                self._active_task = asyncio.create_task(
                    self.graph.ainvoke(graph_input, config=config)
                )
                final_state = await self._await_before_deadline(
                    self._active_task,
                    deadline=pipeline_deadline,
                    component="graph_execution",
                )

            # 确保从 final_state 中提取有效值
            self.state.update(final_state)   # 合并最终状态

            # Do not publish success if cancellation won the race with graph
            # completion.
            if self._cancellation_requested():
                raise asyncio.CancelledError()

            # 优先使用 final_state 中的路径，其次是 self.state
            midi_path = final_state.get("midi_path") or self.state.get("midi_path")
            # 如果仍然为空，尝试从 melody_data 中提取
            if not midi_path:
                melody_data = final_state.get("melody_data") or self.state.get("melody_data")
                if melody_data and isinstance(melody_data, dict):
                    midi_path = melody_data.get("midi_path")
            arranged_midi_path = final_state.get("arranged_midi_path") or self.state.get("arranged_midi_path")

            if self.task.resume_from_node:
                self.state["resume_from_node"] = self.task.resume_from_node
            # Tool callbacks persist directly while the graph is running. Refresh
            # that JSON snapshot before merging it with checkpointed node events.
            self.db.refresh(self.task, ["intermediate_data"])
            persisted_diagnostics = dict(self.task.intermediate_data or {})
            execution_trace = merge_trace_events(
                persisted_diagnostics.get("execution_trace"),
                self.state.get("execution_trace"),
            )
            self.task.intermediate_data = {
                "audio_path": final_state.get("audio_path") or self.state.get("audio_path"),
                "demucs_separated": final_state.get(
                    "demucs_separated", self.state.get("demucs_separated", False)
                ),
                "vocals_path": final_state.get("vocals_path") or self.state.get("vocals_path"),
                "accompaniment_path": (
                    final_state.get("accompaniment_path")
                    or self.state.get("accompaniment_path")
                ),
                "analysis_result": final_state.get("analysis_result") or self.state.get("analysis_result"),
                "melody_data": final_state.get("melody_data") or self.state.get("melody_data"),
                "melody_source_path": (
                    final_state.get("melody_source_path")
                    or self.state.get("melody_source_path")
                ),
                "harmony_source_path": (
                    final_state.get("harmony_source_path")
                    or self.state.get("harmony_source_path")
                ),
                "source_for_melody": (
                    final_state.get("source_for_melody")
                    or self.state.get("source_for_melody")
                ),
                "melody_extractor": (
                    final_state.get("melody_extractor")
                    or self.state.get("melody_extractor")
                ),
                "melody_candidate_summary": (
                    final_state.get("melody_candidate_summary")
                    or self.state.get("melody_candidate_summary")
                    or {}
                ),
                "selected_melody_extractor": (
                    final_state.get("selected_melody_extractor")
                    or self.state.get("selected_melody_extractor")
                ),
                "midi_path": midi_path,
                "arranged_midi_path": arranged_midi_path,
                "tempo": final_state.get("tempo") or self.state.get("tempo"),
                "instrument": final_state.get("instrument") or self.state.get("instrument"),
                "execution_trace": execution_trace,
                "execution_error": None,
            }

            # 同步结果到数据库
            self.task.final_audio_url = final_state.get("final_audio_url")
            self.task.audio_duration = final_state.get("audio_duration")
            # self.task.thinking_process = final_state.get("thinking_process", [])
            if not await self._update_task_status(TaskStatus.completed):
                raise asyncio.CancelledError()

            succeeded_event = create_trace_event(
                task_id=self.task_id,
                kind="task",
                name="agent_execution",
                status="succeeded",
                duration_ms=(time.perf_counter() - execute_started_at) * 1000,
            )
            persist_trace_event(self.task_id, succeeded_event)
            self.state["execution_trace"] = merge_trace_events(
                self.state.get("execution_trace"),
                [succeeded_event],
            )

            # 记录完成消息
            plan = self.state.get("plan", [])
            user_request = self.state.get("user_request", "")
            if plan:
                steps_str = "、".join(plan)
                prompt = (
                    f"用户需求：{user_request}\n"
                    f"执行步骤：{steps_str}\n"
                    "请用一句简短自然的中文总结改编结果，不要提及技术细节。"
                )
                try:
                    summary = await llm_service.chat(
                        [{"role": "user", "content": prompt}],
                        temperature=0.5,
                        max_tokens=100
                    )
                    summary = summary.strip()
                except Exception:
                    summary = "已完成铃声改编。"
            else:
                summary = "任务完成。"

            final_message = (
                f"任务已完成！{summary} "
                f"生成铃声：{self.task.final_audio_url}\n"
                f"时长：{self.task.audio_duration}秒"
            )
            self._update_assistant_message(final_message)
            self._complete_conversation()

            self.db.commit()

            return {
                "success": True,
                "audio_url": self.task.final_audio_url,
                "duration": self.task.audio_duration,
            }

        except asyncio.CancelledError:
            if self._suspend_reason:
                await self._finalize_suspension(execute_started_at)
                return {"success": False, "reason": self._suspend_reason}
            await self._finalize_cancellation(execute_started_at)
            return {"success": False, "reason": "cancelled"}
        except Exception as e:
            if self._suspend_reason:
                await self._finalize_suspension(execute_started_at)
                return {"success": False, "reason": self._suspend_reason}
            if self._cancel_event.is_set() or self._cancellation_requested():
                await self._finalize_cancellation(execute_started_at)
                return {"success": False, "reason": "cancelled"}
            execution_error = build_execution_error(
                e,
                scope="task",
                component="agent_execution",
            )
            execution_error["task_id"] = self.task_id
            if isinstance(e, ExecutionDeadlineExceeded):
                persist_trace_event(
                    self.task_id,
                    create_trace_event(
                        task_id=self.task_id,
                        kind="resilience",
                        name="pipeline_deadline",
                        status="exhausted",
                        duration_ms=(time.perf_counter() - execute_started_at) * 1000,
                        details={
                            "timeout_seconds": self._pipeline_timeout_seconds,
                        },
                        error=execution_error,
                    ),
                )
            failed_event = create_trace_event(
                task_id=self.task_id,
                kind="task",
                name="agent_execution",
                status="failed",
                duration_ms=(time.perf_counter() - execute_started_at) * 1000,
                error=execution_error,
            )
            persist_trace_event(self.task_id, failed_event)
            # Reload the event persisted by this handler and any failing node.
            self.db.refresh(self.task, ["intermediate_data"])
            intermediate = dict(self.task.intermediate_data or {})
            intermediate["execution_error"] = execution_error
            self.task.intermediate_data = intermediate
            public_error_message = redact_text(e)
            self.task.error_message = public_error_message
            if not await self._update_task_status(TaskStatus.failed):
                return {"success": False, "reason": "cancelled"}
            self.db.commit()

            # 记录错误消息到会话
            self._update_assistant_message(f"任务执行失败：{public_error_message}")
            self._complete_conversation()
            raise
        finally:
            if memory_context_token is not None:
                from app.services.memory import reset_agent_context, reset_agent_profile_id

                reset_agent_context(memory_context_token)
                if memory_profile_token is not None:
                    reset_agent_profile_id(memory_profile_token)
            reset_execution_context(execution_context_token)
            self.close()  # 确保执行完毕后关闭会话

    async def _await_before_deadline(
        self,
        awaitable,
        *,
        deadline: float,
        component: str,
    ):
        """Await one pipeline phase without resetting the overall deadline."""

        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            raise ExecutionDeadlineExceeded(
                f"Agent pipeline exceeded {self._pipeline_timeout_seconds:.3f}s "
                f"during {component}"
            )
        try:
            return await asyncio.wait_for(awaitable, timeout=remaining)
        except asyncio.TimeoutError as error:
            # A nested dependency may raise its own TimeoutError before the
            # global deadline. Preserve that exception instead of relabeling it.
            if time.perf_counter() + 0.01 < deadline:
                raise
            raise ExecutionDeadlineExceeded(
                f"Agent pipeline exceeded {self._pipeline_timeout_seconds:.3f}s "
                f"during {component}"
            ) from error

    async def _update_task_status(self, status: TaskStatus) -> bool:
        active_statuses = (
            TaskStatus.pending,
            TaskStatus.planning,
            TaskStatus.executing,
            TaskStatus.waiting_input,
        )
        if status != TaskStatus.cancelled and self._cancel_event.is_set():
            return False

        with self.db.no_autoflush:
            updated = (
                self.db.query(TaskModel)
                .filter(
                    TaskModel.id == self.task_id,
                    TaskModel.status.in_(active_statuses),
                )
                .update(
                    {
                        TaskModel.status: status,
                        TaskModel.updated_at: datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
            )
        if updated != 1:
            self.db.rollback()
            self.db.refresh(self.task, ["status", "updated_at"])
            return self.task.status == status

        self.db.commit()
        self.db.refresh(self.task, ["status", "updated_at"])
        from app.services.task_events import emit_task_status

        emit_task_status(
            self.task_id,
            status.value,
            current_subtask=self.task.current_subtask,
            subtask_progress=self.task.subtask_progress or 0,
            audio_url=self.task.final_audio_url,
            duration=self.task.audio_duration,
            error=self.task.error_message,
        )
        return True

    def _add_thinking_step(self, step: str, content: str, type: str = "info", status: str = None) -> None:
        record_thought(self.task_id, step, content, type, status)

    def _add_assistant_message(self, content: str) -> None:
        """记录助手消息到会话"""
        if not self.conversation_id:
            return

        try:
            message = ConversationMessage(
                conversation_id=self.conversation_id,
                role=MessageRole.assistant,
                content=content,
                task_id=self.task_id,
            )
            self.db.add(message)

            # 更新会话的更新时间
            conversation = self.db.query(Conversation).filter(
                Conversation.id == self.conversation_id
            ).first()
            if conversation:
                conversation.updated_at = datetime.utcnow()

            self.db.commit()
        except Exception as e:
            # 记录消息失败不影响主流程
            print(f"[WARNING] Failed to add assistant message: {e}")

    def _update_assistant_message(self, content: str) -> None:
        """更新已有的 assistant 消息内容"""
        if not self.assistant_message:
            return
        self.assistant_message.content = content
        self.db.commit()

    def _complete_conversation(self) -> None:
        """将会话标记为已完成"""
        if not self.conversation_id:
            return

        try:
            conversation = self.db.query(Conversation).filter(
                Conversation.id == self.conversation_id
            ).first()
            if conversation and conversation.status == ConversationStatus.active:
                conversation.status = ConversationStatus.completed
                self.db.commit()
        except Exception as e:
            print(f"[WARNING] Failed to complete conversation: {e}")

    def close(self):
        """显式关闭会话"""
        if self._owns_db and self.db:
            self.db.close()
            self.db = None

    def __del__(self):
        if hasattr(self, 'db') and self.db:
            self.db.close()
    
    async def _run_subprocess(self, cmd):
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.PIPE, stderr=asyncio.PIPE
        )
        self._subprocesses.append(proc)
        try:
            await proc.communicate()
        finally:
            if proc in self._subprocesses:
                self._subprocesses.remove(proc)

    async def cancel(self):
        """Idempotently cancel planning, graph execution and child processes."""
        self._cancel_event.set()

        if self.db and self.task:
            self.task.error_message = "任务已被用户取消"
        if self.db and self.task and await self._update_task_status(TaskStatus.cancelled):
            if self.assistant_message:
                self.assistant_message.content = "任务已取消"
            self.db.commit()

        # 终止所有子进程
        for proc in list(self._subprocesses):
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            except (ProcessLookupError, RuntimeError):
                pass

        current_task = asyncio.current_task()
        execution_task = self._execution_task
        if (
            execution_task
            and execution_task is not current_task
            and not execution_task.done()
        ):
            execution_task.cancel()
            try:
                await execution_task
            except asyncio.CancelledError:
                pass
        elif self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

    async def suspend(self, reason: str = "runtime_shutdown") -> None:
        """Stop local work without converting the durable task to cancelled."""
        self._suspend_reason = reason
        for proc in list(self._subprocesses):
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            except (ProcessLookupError, RuntimeError):
                pass

        current_task = asyncio.current_task()
        execution_task = self._execution_task
        if execution_task and execution_task is not current_task and not execution_task.done():
            execution_task.cancel()
            try:
                await execution_task
            except asyncio.CancelledError:
                pass
        elif self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass
