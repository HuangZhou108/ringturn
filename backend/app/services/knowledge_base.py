"""
音乐编曲知识库（RAG 用）

存储音乐改编相关的领域知识文档，供 agent 检索。
"""
import re

# 知识文档：标题 + 内容
DOCUMENTS = [
    {
        "title": "青春洋溢/欢快风格的编曲建议",
        "content": "明亮清脆的乐器：Music Box(八音盒)、Glockenspiel(钟琴)、Bright Acoustic Piano、Electric Piano、Marimba、Vibraphone。速度偏快，约为检测 BPM 的 110%~120%。用高音区、轻快节奏营造青春活力。",
    },
    {
        "title": "悠扬/抒情风格的编曲建议",
        "content": "柔美乐器：Violin(小提琴)、Acoustic Grand Piano、Celesta、Orchestral Harp、Warm Pad。速度偏慢（80~96 BPM）。用长音、延音营造悠扬感，避免密集短音符。",
    },
    {
        "title": "忧伤/伤感风格的编曲建议",
        "content": "温暖低沉乐器：Cello(大提琴)、Clarinet、String Ensemble、Acoustic Grand Piano。速度偏慢。用中低音区、连音表达情感。",
    },
    {
        "title": "激昂/史诗风格的编曲建议",
        "content": "Brass Section(铜管)、String Ensemble(弦乐合奏)、Overdriven Guitar。速度中快。用强力度、厚和声营造气势。",
    },
    {
        "title": "手机铃声编曲技巧",
        "content": "1. 截取副歌/高潮最有记忆点的乐句。2. 开头快速进入主题，避免长前奏。3. 结尾自然收束或淡出，方便循环。4. 音量适中，外放清晰不刺耳。5. 时长常用 30~60 秒。",
    },
    {
        "title": "移调与音域技巧",
        "content": "旋律整体偏低可上移八度(+12)，偏高可下移(-12)。移调范围通常 -12~+12 半音。目标是让旋律落在目标乐器的舒适音域，例如小提琴适合中高音区。",
    },
    {
        "title": "音符连贯性处理",
        "content": "用延音(sustain)、连奏(legato)让音符衔接连贯，符合悠扬风格。避免大量短碎音符。可合并相邻同音高音符。",
    },
]


def _tokenize(text: str) -> set:
    """简单分词：按非字母数字切分（兼容中英文）。"""
    return set(re.findall(r"[\w一-鿿]+", text.lower()))


def retrieve_knowledge(query: str, top_k: int = 3) -> list[dict]:
    """
    根据查询检索相关知识文档（简单关键词重叠打分）。

    Returns:
        list[dict]: 命中的知识文档（按相关度降序）
    """
    query_words = _tokenize(query or "")
    if not query_words:
        return DOCUMENTS[:top_k]

    scored = []
    for doc in DOCUMENTS:
        doc_words = _tokenize(doc["title"] + " " + doc["content"])
        overlap = len(query_words & doc_words)
        score = overlap / max(1, len(query_words))
        scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    return [doc for score, doc in scored[:top_k] if score > 0]


def format_knowledge(docs: list[dict]) -> str:
    """把检索到的知识文档格式化成可注入提示词的文本。"""
    if not docs:
        return ""
    return "\n".join(f"【{d['title']}】{d['content']}" for d in docs)
