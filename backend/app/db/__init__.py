"""数据库初始化和会话管理"""

from app.core.config import get_settings, ensure_directories
from app.db.session import init_db, enable_wal_mode

settings = get_settings()
ensure_directories()
init_db()
enable_wal_mode()
