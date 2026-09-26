"""
Agent执行器

协调 LangGraph 图执行，管理状态初始化、计划生成和结果同步
"""

import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.agent.state import AgentState, TaskStep
from app.agent.graph import get_agent_graph
from app.models import Task as TaskModel, TaskStatus
from app.agent.thinking_utils import record_thought
from app.models import Task as TaskModel, TaskStatus, Conversation, ConversationMessage, MessageRole, ConversationStatus
import threading
from asyncio import Task as AsyncioTask
from app.services.llm_service import llm_service

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
    def __init__(self, task_id: str, db: Session = None, conversation_id: str = None):
        self.task_id = task_id
        self.db = db if db is not None else SessionLocal(expire_on_commit=False)
        self._owns_db = db is None  # 标记是否自己创建的会话
        self.conversation_id = conversation_id
        self._active_task: Optional[AsyncioTask] = None
        self._cancel_event = asyncio.Event()   # 用于通知内部协程取消
        self._subprocesses = []   # 保存子进程对象

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
            "analysis_result": None,
            "melody_data": None,
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
            "created_at": self.task.created_at,
            "updated_at": datetime.utcnow(),
        }

        # 如果是反馈任务，从父任务的 intermediate_data 加载
        if self.task.parent_task_id and self.task.intermediate_data:
            inter = self.task.intermediate_data
            print(f"[DEBUG] intermediate_data: {inter}")
            state.update({
                "audio_path": inter.get("audio_path"),
                "analysis_result": inter.get("analysis_result"),
                "melody_data": inter.get("melody_data"),
                "midi_path": inter.get("midi_path"),
                "arranged_midi_path": inter.get("arranged_midi_path"),
                "tempo": inter.get("tempo", 120),
                "instrument": inter.get("instrument", "Acoustic Piano"),
            })
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
            print(f"[PLAN] extract_duration failed: {e}")

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

    async def execute(self) -> dict:
        """执行任务：调用 LangGraph 图"""
        try:
            # 注入 Agent 记忆（全局偏好 + 历史画像），供本次任务所有 LLM 调用使用
            try:
                from app.services.memory import build_agent_context, set_agent_context
                ctx = await asyncio.to_thread(build_agent_context, self.state.get("profile_id"))
                if ctx:
                    set_agent_context(ctx)
            except Exception as e:
                print(f"[MEMORY] build_agent_context failed: {e}")

            # 检查是否已取消
            if self.task.status == TaskStatus.cancelled:
                return {"success": False, "reason": "cancelled"}
            
            # 将反馈指定的起始节点注入 state
            if self.task.resume_from_node:
                self.state["resume_from_node"] = self.task.resume_from_node
                print(f"[AGENT] Will resume from node: {self.task.resume_from_node}")

            await self._update_task_status(TaskStatus.planning)
            await self._plan()

            await self._update_task_status(TaskStatus.executing)
            # 异步获取图实例
            self.graph = await get_agent_graph()
            config = {"configurable": {"thread_id": self.task_id}}
            # final_state = await self.graph.ainvoke(self.state, config=config)

            # 创建 asyncio 任务
            self._active_task = asyncio.create_task(
                self.graph.ainvoke(self.state, config=config)
            )
            final_state = await self._active_task

            # 确保从 final_state 中提取有效值
            self.state.update(final_state)   # 合并最终状态

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
            self.task.intermediate_data = {
                "audio_path": final_state.get("audio_path") or self.state.get("audio_path"),
                "analysis_result": final_state.get("analysis_result") or self.state.get("analysis_result"),
                "melody_data": final_state.get("melody_data") or self.state.get("melody_data"),
                "midi_path": midi_path,
                "arranged_midi_path": arranged_midi_path,
                "tempo": final_state.get("tempo") or self.state.get("tempo"),
                "instrument": final_state.get("instrument") or self.state.get("instrument"),
            }

            # 检查是否在运行中被取消
            if self._cancel_event.is_set():
                raise asyncio.CancelledError()

            # 同步结果到数据库
            self.task.final_audio_url = final_state.get("final_audio_url")
            self.task.audio_duration = final_state.get("audio_duration")
            # self.task.thinking_process = final_state.get("thinking_process", [])
            await self._update_task_status(TaskStatus.completed)

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
            await self._update_task_status(TaskStatus.cancelled)
            self.task.error_message = "任务已被用户取消"
            self.db.commit()
            return {"success": False, "reason": "cancelled"}
        except Exception as e:
            if self._cancel_event.is_set():
                await self._update_task_status(TaskStatus.cancelled)
                return {"success": False, "reason": "cancelled"}
            self.db.refresh(self.task)
            if self.task.status == TaskStatus.cancelled:
                return {"success": False, "reason": "cancelled"}
            await self._update_task_status(TaskStatus.failed)
            self.task.error_message = str(e)
            self.db.commit()

            # 记录错误消息到会话
            self._update_assistant_message(f"任务执行失败：{str(e)}")
            self._complete_conversation()
            raise
        finally:
            self.close()  # 确保执行完毕后关闭会话

    async def _update_task_status(self, status: TaskStatus) -> None:
        self.task.status = status
        self.task.updated_at = datetime.utcnow()
        self.db.commit()

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
        """取消正在执行的任务"""
        # 终止所有子进程
        for proc in self._subprocesses:
            try:
                proc.terminate()
                await proc.wait()
            except:
                pass
        self._cancel_event.set()
        if self.assistant_message:
            self.assistant_message.content = "任务已取消"
            self.db.commit()
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            # 等待任务真正取消
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass