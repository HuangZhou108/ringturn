"""
Agent执行器

负责协调整个Agent工作流
"""

import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.agent.state import AgentState, TaskStep
from app.agent.tools import tool_gateway
from app.agent.nodes import NODE_HANDLERS
from app.db.session import SessionLocal
from app.models import Task as TaskModel, TaskStatus

class RingtoneParams:
    """铃声参数"""
    def __init__(self, task: TaskModel):
        params = task.ringtone_params or {}
        
        self.instrument = params.get("instrument", "Acoustic Piano")
        self.duration = params.get("duration", 30)
        self.tempo = params.get("tempo", 120)
        self.filename = params.get("filename", "ringtone")
        # 文件ID（从 source_value 获取，当有上传文件时）
        self.file_id = task.source_value

class AgentExecutor:
    """Agent执行器"""

    def __init__(self, task_id: str, db: Session = None):
        self.task_id = task_id
        self.db = db or SessionLocal()

        # 获取任务
        self.task = self.db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not self.task:
            raise ValueError(f"任务不存在: {task_id}")

        # 解析铃声参数
        self.ringtone_params = RingtoneParams(self.task)

        # 初始化状态
        self.state = self._init_state()

    def _init_state(self) -> AgentState:
        """初始化Agent状态"""
        state: AgentState = {
            "task_id": self.task.id,
            "user_id": self.task.user_id,
            "user_request": self.task.user_request,
            "source_type": self.task.source_type,
            "source_value": self.task.source_value,
            # 铃声参数
            "instrument": self.ringtone_params.instrument,
            "duration": self.ringtone_params.duration,
            "tempo": self.ringtone_params.tempo,
            "filename": self.ringtone_params.filename,
            # 文件ID（用于获取上传的音频文件）
            "file_id": self.ringtone_params.file_id,
            # 中间产物
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
        return state

    async def execute(self) -> dict:
        """
        执行任务

        Returns:
            dict: 执行结果
        """
        try:
            # 1. 规划阶段
            await self._update_task_status(TaskStatus.planning)
            await self._plan()

            # 2. 执行阶段
            await self._update_task_status(TaskStatus.executing)
            await self._execute_steps()

            # 3. 完成
            await self._update_task_status(TaskStatus.completed)
            return {
                "success": True,
                "audio_url": self.task.final_audio_url,
                "duration": self.task.audio_duration,
            }

        except Exception as e:
            await self._update_task_status(TaskStatus.failed)
            self.task.error_message = str(e)
            self.db.commit()
            raise

    async def execute_optimization(self, feedback: str) -> dict:
        """
        执行优化任务（基于用户反馈）

        Args:
            feedback: 用户反馈内容

        Returns:
            dict: 执行结果
        """
        # 添加反馈到历史
        self.state["feedback_history"].append({
            "feedback": feedback,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # 解析反馈并调整计划
        # 使用LLM辅助解析
        parsed = await tool_gateway.parse_user_request(
            f"基于反馈调整: {feedback}"
        )

        # 更新编排参数
        if parsed.get("instruments"):
            self.state["arrangement_params"] = parsed

        # 直接执行arrange和render步骤（不重复分析）
        self.state["current_step"] = TaskStep.ARRANGE.value
        self.state["current_step_index"] = 4

        try:
            await self._update_task_status(TaskStatus.executing)

            # 重新执行改编步骤
            await self._execute_step(TaskStep.ARRANGE.value)
            await self._execute_step(TaskStep.RENDER.value)
            await self._execute_step(TaskStep.CHECK_QUALITY.value)

            # 检查反思结果
            if self.state.get("needs_revision"):
                # 再次失败，更新错误信息
                self.task.error_message = "多次优化后质量仍不达标"
                self.db.commit()

            await self._update_task_status(TaskStatus.completed)
            return {
                "success": True,
                "audio_url": self.task.final_audio_url,
                "duration": self.task.audio_duration,
            }

        except Exception as e:
            await self._update_task_status(TaskStatus.failed)
            self.task.error_message = str(e)
            self.db.commit()
            raise

    async def _plan(self) -> None:
        """
        规划阶段

        使用LLM将用户需求分解为执行步骤
        """
        from app.services.llm_service import llm_service

        user_request = self.state.get("user_request", "")

        # 调用LLM生成计划
        plan = await llm_service.generate_plan(user_request)

        self.state["plan"] = plan
        self.task.plan = plan
        self.db.commit()

    async def _execute_steps(self) -> None:
        """
        执行所有步骤
        """
        plan = self.state["plan"]
        total_steps = len(plan)

        for idx, step_name in enumerate(plan):
            self.state["current_step_index"] = idx
            self.state["current_step"] = step_name

            try:
                # 更新子步骤状态
                self.task.current_subtask = step_name
                self.task.subtask_progress = int((idx + 1) / total_steps * 90)
                self.db.commit()

                # 执行当前步骤
                await self._execute_step(step_name)

                # 记录结果
                self.state["step_results"][step_name] = "completed"

                # 检查反思结果
                if step_name == TaskStep.CHECK_QUALITY.value:
                    if self.state.get("needs_revision"):
                        # 质量不达标，尝试优化
                        # 这里可以添加自动优化逻辑
                        pass

            except Exception as e:
                # 记录错误
                self.state["error"] = str(e)
                self.state["step_results"][step_name] = f"failed: {str(e)}"
                self.task.error_message = str(e)
                self.db.commit()
                raise

        # 全部完成，同步结果到task
        self.task.subtask_progress = 100
        self.task.final_audio_url = self.state.get("final_audio_url")
        self.task.audio_duration = self.state.get("audio_duration")
        self.db.commit()

    async def _execute_step(self, step: str) -> None:
        """
        执行单个步骤

        Args:
            step: 步骤名称
        """
        handler = NODE_HANDLERS.get(step)
        if not handler:
            raise ValueError(f"未知步骤: {step}")

        await handler(self.state, self.db, tool_gateway)

        self.db.commit()

    async def _update_task_status(self, status: TaskStatus) -> None:
        """更新任务状态"""
        self.task.status = status
        self.task.updated_at = datetime.utcnow()
        self.db.commit()

    def __del__(self):
        """清理资源"""
        if hasattr(self, 'db') and self.db:
            self.db.close()

async def run_agent_task(task_id: str) -> None:
    """
    运行Agent任务

    独立的异步任务函数

    Args:
        task_id: 任务ID
    """
    executor = AgentExecutor(task_id)
    try:
        await executor.execute()
    except Exception as e:
        print(f"[ERROR] Task {task_id} failed: {e}")
        raise
