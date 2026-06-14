from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
import json

from app.db.session import get_db
from app.models import Task, TaskStatus, Feedback, ConversationMessage, MessageRole
from app.schemas import (
    FeedbackCreate,
    FeedbackCreateResponse,
    FeedbackResponse,
    FeedbackListResponse,
)
from app.services.llm_service import llm_service
from app.agent.agent_executor import AgentExecutor

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 定义反馈节点判断函数
async def determine_resume_node(feedback: str) -> str:
    """根据反馈内容判断从哪个节点开始重新执行"""
    prompt = f"""
用户对生成的铃声提出反馈："{feedback}"
请分析用户不满意的环节，从以下节点中选择最合适的重新开始执行节点：
- fetch_source: 需要更换音频源
- analyze_structure: 对音乐结构分析不满意（BPM、调性等）
- extract_melody: 对提取的主旋律不满意
- generate_midi: 对生成的MIDI不满意
- arrange: 对乐器改编不满意（乐器选择、节奏编排）
- render: 对渲染的音频质量不满意（音色、时长截取）
- check_quality: 对整体质量不满意需要重试

注意：如果用户要求更换乐器或调整速度，应选择 "arrange"。
如果用户对旋律本身不满意，选择 "extract_melody"。
如果用户对音频渲染质量不满意，选择 "render"。
如果用户对于音频切割的选择不满意，选择"render"。
只输出节点名称，不要输出其他内容。
"""
    response = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.2)
    node = response.strip().lower()
    valid_nodes = ["fetch_source", "analyze_structure", "extract_melody", "generate_midi", "arrange", "render", "check_quality"]
    return node if node in valid_nodes else "arrange"


# 添加参数提取函数
async def extract_params_from_feedback(feedback: str, current_params: dict) -> dict:
    """根据反馈文本提取需要修改的参数（如 instrument, tempo, duration 等）"""
    prompt = f"""用户对生成的铃声提出反馈："{feedback}"
当前参数：{json.dumps(current_params, ensure_ascii=False)}
请分析用户希望修改哪些参数，只返回需要修改的字段。可能的字段有：instrument, tempo, duration, filename 等。
以 JSON 格式返回，例如：{{"instrument": "Violin"}} 或 {{"tempo": 140}}。
如果用户没有明确要求修改某个参数，则不要包含该字段。只输出 JSON，不要有其他内容。"""
    try:
        response = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.2)
        # 尝试解析 JSON
        updates = json.loads(response.strip())
        # 只保留合法的参数键
        valid_keys = {"instrument", "tempo", "duration", "filename"}
        return {k: v for k, v in updates.items() if k in valid_keys}
    except Exception as e:
        print(f"[WARN] 提取反馈参数失败: {e}")
        return {}
    

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
    
    # 1. 调用 LLM 分析反馈，确定起始节点
    resume_node = await determine_resume_node(request.feedback)

    # 2. 创建子任务
    # 提取参数更新
    # 合并参数：如果请求中提供了 params，则覆盖父任务的对应字段
    new_params = dict(parent_task.ringtone_params or {})
    if request.params:
        for key, value in request.params.items():
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
    from app.agent.thinking_utils import record_thought
    record_thought(new_task_id, "feedback", f"根据反馈 '{request.feedback}'，选择从节点 '{resume_node}' 重新开始。")

    # 3. 从父任务复制中间数据
    child_task.intermediate_data = parent_task.intermediate_data

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

    # 5. 异步执行子任务（需要从 tasks 模块导入 run_agent_task）
    from app.api.v1.endpoints.tasks import run_agent_task
    background_tasks.add_task(run_agent_task, new_task_id)

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
