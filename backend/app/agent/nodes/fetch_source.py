from pathlib import Path
from app.agent.state import AgentState
from app.services.file_service import file_service
from app.agent.thinking_utils import record_thought

async def fetch_source_node(state: AgentState) -> dict:
    """
    节点1: 获取音频源

    根据source_type获取音频文件
    """
    source_type = state.get("source_type", "upload")
    source_value = state.get("source_value")
    task_id = state["task_id"]

    if source_type == "upload":
        # 获取上传文件
        if not source_value:
            raise ValueError("上传类型需要提供source_value（文件ID）")

        file_path = file_service.get_upload_path(source_value)
        if not file_path:
            raise ValueError(f"文件不存在: {source_value}")
        
        # 尝试加载音频文件，验证是否可读
        try:
            import librosa
            # 仅加载前 1 秒进行快速验证
            y, sr = librosa.load(str(file_path), duration=1, sr=22050)
            if y is None or len(y) == 0:
                raise RuntimeError("音频文件内容为空")
        except Exception as e:
            raise RuntimeError(f"无法打开或解析上传的音频文件: {e}")

        audio_path = str(file_path)
        record_thought(task_id, "fetch_source", f"音频源获取成功: {file_path}")
        return {"audio_path": audio_path}

    elif source_type == "search":
        # TODO: 实现搜索功能
        raise NotImplementedError("search类型暂未实现")

    else:
        raise ValueError(f"不支持的source_type: {source_type}")
