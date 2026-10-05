export interface ApiResponse<T = unknown> {
    code: number
    data: T
    message: string | null
}

// 任务状态
export type TaskStatus =
    | 'pending'
    | 'planning'
    | 'executing'
    | 'waiting_input'
    | 'completed'
    | 'failed'
    | 'cancelled'

// 来源类型
export type SourceType = 'upload' | 'link' | 'search'

export interface AgentTraceError {
    code: string
    type: string
    message: string
    retryable: boolean
}

export interface AgentTraceEvent {
    version: number
    event_id: string
    kind: 'lifecycle' | 'node' | 'tool' | 'routing'
    name: string
    status: 'running' | 'success' | 'failed' | 'cancelled'
    parent_name?: string
    started_at: string
    finished_at?: string
    duration_ms?: number
    metadata?: Record<string, unknown>
    error?: AgentTraceError
}

// 任务创建请求
export interface CreateTaskRequest {
    user_request: string
    source_type?: SourceType
    source_value?: string
    // 铃声参数，使用动态参数
    params?: Record<string, any>;
}

// 任务创建响应
export interface CreateTaskResponse {
    task_id: string
    status: TaskStatus
    created_at: string
}

// 任务详情
export interface Task {
    id: string
    profile_id: number
    parent_task_id?: string
    user_request: string
    source_type: SourceType
    source_value?: string
    status: TaskStatus
    current_subtask?: string
    subtask_progress: number
    plan?: unknown
    current_plan_index: number
    thread_id?: string
    final_audio_url?: string
    audio_duration?: number
    conversation_id?: string
    created_at: string
    updated_at: string
    error_message?: string
}

// 任务状态信息
export interface TaskStatusInfo {
    task_id: string
    status: TaskStatus
    current_subtask?: string
    subtask_progress: number
    message?: string
    thinking_process?: { step: string; content: string; timestamp: string }[]
}

// 任务生成结果
export interface TaskResult {
    audio_url?: string
    duration?: number
    format?: string
    thinking_process?: { step: string; content: string; timestamp: string }[]
}

// 反馈
export interface Feedback {
    id: number
    task_id: string
    content: string
    created_at: string
}

// 任务取消结果
export interface TaskCancelResult {
    task_id: string
    previous_status: string
    current_status: string
}

// 任务列表响应
export interface TaskListResponse {
    total: number
    page: number
    page_size: number
    tasks: TaskListItem[]
}

export interface TaskListItem {
    task_id: string
    user_request: string
    status: TaskStatus
    final_audio_url?: string | null
    audio_duration?: number | null
    created_at: string
}

// 偏好
export interface Preference {
    id: number
    profile_id: number
    key: string
    value: unknown
}

export interface UploadResult {
    file_id: string
    filename: string
    file_size: number
    format: string
    duration: number
    created_at: string
}

// 聊天消息类型
export interface Message {
    id: string;
    type: 'ai' | 'user';
    content?: string;
    deepThinking?: string;
    fileName?: string;
    fileInfo?: string;
    userFile?: string;
    audioFileId?: string;
    taskId?: string;
    thinkingProcess?: {
        step: string;
        content: string;
        timestamp: string;
        type?: 'info' | 'llm' | 'tool_call' | 'tool_result';
        status?: 'success' | 'failed' | 'pending' | 'retry';
    }[];
    showThinking?: boolean;
}

// 会话相关类型
export interface Conversation {
    conversation_id: string;
    title: string;
    status: 'active' | 'completed';
    created_at: string;
    updated_at: string;
}

export interface ConversationListItem {
    conversation_id: string;
    title: string;
    status: string;
    message_count: number;
    last_message: string | null;
    created_at: string;
    updated_at: string;
}

export interface ConversationDetail {
    conversation_id: string;
    title: string;
    status: string;
    messages: ConversationMessage[];
    created_at: string;
    updated_at: string;
}

export interface ConversationMessage {
    id: number;
    role: 'user' | 'assistant';
    content: string;
    task_id: string | null;
    created_at: string;
}

// 更新任务创建请求
export interface CreateTaskRequest {
    user_request: string
    conversation_id?: string  // 关联的会话ID
    source_type?: SourceType
    source_value?: string
    params?: {
        instrument?: string
        duration?: number
        tempo?: number
        filename?: string
        [key: string]: any
    }
}

// 更新任务创建响应
export interface CreateTaskResponse {
    task_id: string
    conversation_id: string  // 新增
    status: TaskStatus
    created_at: string
}

// Profile 相关类型
export interface Profile {
    profile_id: number
    name: string
    is_active: boolean
    created_at: string
}

export interface ProfileListResponse {
    data: Profile[]
}

export interface ProfileActiveResponse {
    data: Profile
}

export interface ProfileTasksResponse {
    total: number
    page: number
    page_size: number
    tasks: TaskListItem[]
}

export interface ProfilePreferences {
    default_instrument?: string
    disliked_instruments?: string[]
    default_duration?: number
    default_tempo?: number
    [key: string]: any
}

export interface PreferenceAIRecommendation {
    instrument: string | null;
    tempo: number | null;
    duration: number | null;
    style_tags: string[];
}

export interface PreferenceUserOverrides {
    use_ai_preferences: boolean;
    instrument: string | null;
    tempo: number | null;
    duration: number | null;
    style_tags: string[];
}

export interface PreferenceResponse {
    ai_recommendation: PreferenceAIRecommendation;
    user_overrides: PreferenceUserOverrides;
    effective: PreferenceAIRecommendation;
}

export interface PreferenceUpdateRequest {
    use_ai_preferences?: boolean;
    instrument?: string | null;
    tempo?: number | null;
    duration?: number | null;
    style_tags?: string[] | null;
}

export interface GraphConfig {
    version?: number;
    name?: string;
    entry: string;
    exit?: string;
    nodes: Array<{ id: string; type?: string }>;
    edges?: Array<{ from: string; to: string }>;
    conditional_edges?: Array<{ from: string; condition: string; mapping: Record<string, string> }>;
    default_edges?: Array<{ from: string; to: string }>;
}
