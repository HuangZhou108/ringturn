import uuid
from datetime import datetime

from app.agent.agent_executor import AgentExecutor
from app.agent.trace import without_execution_diagnostics
from app.db.session import get_db
from app.models import (ConversationMessage, Feedback, HumanIntervention,
                        HumanInterventionStatus, MessageRole, Task, TaskStatus)
from app.schemas import (FeedbackCreate, FeedbackCreateResponse,
                         FeedbackListResponse, FeedbackResponse,
                         HumanInterventionAnswer, HumanInterventionCreate)
from app.services.feedback_analysis import analyze_feedback, sanitize_feedback_params
from app.services.task_events import emit_task_event, emit_task_status
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 定义反馈节点判断函数
async def determine_resume_node(feedback: str) -> str:
    """Compatibility wrapper around the structured feedback analyzer."""
    return (await analyze_feedback(feedback, {})).resume_from_node


# 添加参数提取函数
async def extract_params_from_feedback(feedback: str, current_params: dict) -> dict:
    """Compatibility wrapper returning validated parameter updates."""
    return (await analyze_feedback(feedback, current_params)).params
    

@router.post("/{task_id}/feedback")
async def submit_feedback(
    task_id: str,
    request: FeedbackCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    提交反馈（创建子任务优化）

    根据用户的反馈意见，创建一个新的子任务进行优化
    """
    # 验证父任务存在
    parent_task = db.query(Task).filter(Task.id == task_id).first()
    if not parent_task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    if parent_task.status not in {TaskStatus.completed, TaskStatus.failed}:
        raise HTTPException(status_code=409, detail="只能对已结束的任务提交优化反馈")
    
    # 一次结构化调用同时决定重入节点与参数，避免两次 LLM 结果互相矛盾。
    decision = await analyze_feedback(
        request.feedback,
        dict(parent_task.ringtone_params or {}),
    )
    resume_node = decision.resume_from_node

    # 2. 创建子任务
    # 提取参数更新
    # 合并参数：如果请求中提供了 params，则覆盖父任务的对应字段
    new_params = dict(parent_task.ringtone_params or {})
    new_params.update(decision.params)
    if request.params:
        for key, value in sanitize_feedback_params(request.params).items():
            if value is not None and value != "":
                new_params[key] = value

    new_task_id = str(uuid.uuid4())
    child_task = Task(
        id=new_task_id,
        profile_id=parent_task.profile_id,
        parent_task_id=parent_task.id,
        user_request=request.feedback,
        source_type=parent_task.source_type,
        source_value=parent_task.source_value,        # 复用音频文件ID
        ringtone_params=new_params,  # 继承参数，可后续覆盖
        status=TaskStatus.pending,
        resume_from_node=resume_node,
    )
    db.add(child_task)
    db.add(Feedback(task_id=parent_task.id, content=request.feedback))

    # 3. 从父任务复制中间数据
    child_task.intermediate_data = without_execution_diagnostics(
        parent_task.intermediate_data
    )

    # 4. 在同一会话中添加消息
    conv_msg = db.query(ConversationMessage).filter(
        ConversationMessage.task_id == parent_task.id,
        ConversationMessage.role == MessageRole.user
    ).first()
    if conv_msg:
        conversation_id = conv_msg.conversation_id
        # 用户反馈消息
        user_msg = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.user,
            content=request.feedback,
            task_id=new_task_id,
        )
        db.add(user_msg)
        # 助手占位消息
        assistant_msg = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.assistant,
            content="根据您的反馈正在优化...",
            task_id=new_task_id,
        )
        db.add(assistant_msg)

    db.commit()

    from app.agent.thinking_utils import record_thought
    record_thought(
        new_task_id,
        "feedback",
        f"已记录用户反馈，选择从节点 '{resume_node}' 重新开始。",
    )
    emit_task_event(
        parent_task.id,
        "feedback_submitted",
        {"child_task_id": new_task_id, "resume_from_node": resume_node},
    )

    # 5. 持久化调度器负责去重执行与重启恢复。
    from app.api.v1.endpoints.tasks import schedule_agent_task
    schedule_agent_task(new_task_id)

    return {
        "code": 200,
        "data": {"task_id": new_task_id, "parent_task_id": task_id, "status": child_task.status.value},
        "message": "反馈已提交"
    }

@router.get("/{task_id}/feedbacks", response_model=FeedbackListResponse)
async def get_task_feedbacks(
    task_id: str,
    db: Session = Depends(get_db),
):
    """
    获取任务的反馈历史
    """
    # 验证任务存在
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    feedbacks = db.query(Feedback).filter(
        Feedback.task_id == task_id
    ).order_by(Feedback.created_at.desc()).all()

    feedback_items = [
        FeedbackResponse(
            id=f.id,
            task_id=f.task_id,
            content=f.content,
            created_at=f.created_at,
        )
        for f in feedbacks
    ]

    return FeedbackListResponse(
        total=len(feedback_items),
        feedbacks=feedback_items,
    )


@router.post("/{task_id}/interventions")
async def request_human_intervention(
    task_id: str,
    request: HumanInterventionCreate,
    db: Session = Depends(get_db),
):
    """Pause active execution and persist a question for human input."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    active_statuses = (
        TaskStatus.pending,
        TaskStatus.planning,
        TaskStatus.executing,
    )
    previous_status = task.status
    updated = (
        db.query(Task)
        .filter(Task.id == task_id, Task.status.in_(active_statuses))
        .update(
            {Task.status: TaskStatus.waiting_input, Task.updated_at: datetime.utcnow()},
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="任务当前状态无法请求人工介入")

    intervention = HumanIntervention(
        id=str(uuid.uuid4()),
        task_id=task_id,
        question=request.question,
        resume_from_node=request.resume_from_node,
        status=HumanInterventionStatus.open,
    )
    db.add(intervention)
    db.commit()
    db.refresh(intervention)

    emit_task_status(
        task_id,
        TaskStatus.waiting_input.value,
        previous_status=previous_status.value,
        intervention_id=intervention.id,
        question=intervention.question,
        resume_from_node=intervention.resume_from_node,
    )

    from app.api.v1.endpoints.tasks import _running_tasks
    executor = _running_tasks.get(task_id)
    if executor:
        await executor.suspend("waiting_input")

    return {
        "code": 200,
        "data": _serialize_intervention(intervention),
        "message": "任务已暂停，等待人工输入。",
    }


@router.post("/{task_id}/interventions/{intervention_id}/response")
async def answer_human_intervention(
    task_id: str,
    intervention_id: str,
    request: HumanInterventionAnswer,
    db: Session = Depends(get_db),
):
    """Persist the answer and resume the same task through the scheduler."""
    task = db.query(Task).filter(Task.id == task_id).first()
    intervention = db.query(HumanIntervention).filter(
        HumanIntervention.id == intervention_id,
        HumanIntervention.task_id == task_id,
    ).first()
    if not task or not intervention:
        raise HTTPException(status_code=404, detail="人工介入请求不存在")
    if (
        intervention.status != HumanInterventionStatus.open
        or task.status != TaskStatus.waiting_input
    ):
        raise HTTPException(status_code=409, detail="人工介入请求已经处理或任务不可恢复")

    decision = await analyze_feedback(request.response, task.ringtone_params or {})
    params = dict(task.ringtone_params or {})
    params.update(decision.params)
    if request.params:
        params.update(sanitize_feedback_params(request.params))
    resume_node = intervention.resume_from_node or decision.resume_from_node

    transitioned = (
        db.query(Task)
        .filter(Task.id == task_id, Task.status == TaskStatus.waiting_input)
        .update(
            {
                Task.status: TaskStatus.pending,
                Task.ringtone_params: params,
                Task.resume_from_node: resume_node,
                Task.error_message: None,
                Task.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    if transitioned != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")

    intervention.response = request.response
    intervention.status = HumanInterventionStatus.responded
    intervention.responded_at = datetime.utcnow()
    db.add(Feedback(task_id=task_id, content=request.response))
    assistant_message = db.query(ConversationMessage).filter(
        ConversationMessage.task_id == task_id,
        ConversationMessage.role == MessageRole.assistant,
    ).first()
    if assistant_message:
        assistant_message.content = "已收到补充信息，正在恢复任务..."
    db.commit()
    db.refresh(intervention)

    emit_task_event(
        task_id,
        "intervention_answered",
        {
            "intervention_id": intervention.id,
            "resume_from_node": resume_node,
        },
    )
    emit_task_status(task_id, TaskStatus.pending.value)

    from app.api.v1.endpoints.tasks import schedule_agent_task
    schedule_agent_task(task_id)
    return {
        "code": 200,
        "data": _serialize_intervention(intervention),
        "message": "补充信息已接收，任务已恢复调度。",
    }


@router.get("/{task_id}/interventions")
async def list_human_interventions(
    task_id: str,
    db: Session = Depends(get_db),
):
    if not db.query(Task).filter(Task.id == task_id).first():
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    interventions = db.query(HumanIntervention).filter(
        HumanIntervention.task_id == task_id
    ).order_by(HumanIntervention.created_at.asc()).all()
    return {
        "code": 200,
        "data": [_serialize_intervention(item) for item in interventions],
        "message": "获取人工介入记录成功。",
    }


def _serialize_intervention(intervention: HumanIntervention) -> dict:
    return {
        "intervention_id": intervention.id,
        "task_id": intervention.task_id,
        "status": intervention.status.value,
        "question": intervention.question,
        "response": intervention.response,
        "resume_from_node": intervention.resume_from_node,
        "created_at": intervention.created_at.isoformat(),
        "responded_at": (
            intervention.responded_at.isoformat()
            if intervention.responded_at
            else None
        ),
    }
