"""
任务管理器 - 自主编码 Agent 核心组件
Task Manager for Autonomous Coding Agent

P0 修复：添加文件锁机制，确保并发安全
P1 修复：添加结构化日志
"""

import json
import fcntl
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

# 配置日志
logger = logging.getLogger(__name__)


class TaskManager:
    """任务列表管理器"""
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.task_file = self.project_dir / "feature_list.json"
        self.progress_file = self.project_dir / "claude-progress.txt"
        self.spec_file = self.project_dir / "app_spec.txt"
        self._lock_path = self.project_dir / ".task_manager.lock"
    
    @contextmanager
    def _file_lock(self):
        """文件锁上下文管理器 - P0 修复"""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, 'w') as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    
    def create_tasks(self, tasks: list) -> bool:
        """创建任务列表 - P0 修复：添加文件锁"""
        with self._file_lock():
            try:
                self.project_dir.mkdir(parents=True, exist_ok=True)
                with open(self.task_file, 'w', encoding='utf-8') as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
                logger.info(f"创建任务列表成功：{len(tasks)} 个任务")
                return True
            except Exception as e:
                logger.error(f"创建任务列表失败：{e}")
                return False
    
    def load_tasks(self) -> list:
        """加载任务列表 - P0 修复：添加文件锁"""
        with self._file_lock():
            if not self.task_file.exists():
                logger.debug("任务列表文件不存在")
                return []
            try:
                with open(self.task_file, 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
                logger.debug(f"加载任务列表成功：{len(tasks)} 个任务")
                return tasks
            except Exception as e:
                logger.error(f"加载任务列表失败：{e}")
                return []
    
    def get_pending_tasks(self) -> list:
        """获取待处理任务"""
        tasks = self.load_tasks()
        return [t for t in tasks if t['status'] == 'pending']
    
    def get_task_by_id(self, task_id: int) -> Optional[dict]:
        """根据 ID 获取任务"""
        tasks = self.load_tasks()
        for task in tasks:
            if task.get('id') == task_id:
                return task
        return None
    
    def update_task_status(self, task_id: int, status: str, notes: str = None) -> bool:
        """更新任务状态 - P0 修复：添加文件锁和原子操作"""
        with self._file_lock():
            tasks = self.load_tasks()
            for task in tasks:
                if task.get('id') == task_id:
                    task['status'] = status
                    if notes:
                        task['notes'] = notes
                    task['updated_at'] = datetime.now().isoformat()
                    try:
                        with open(self.task_file, 'w', encoding='utf-8') as f:
                            json.dump(tasks, f, indent=2, ensure_ascii=False)
                        return True
                    except Exception as e:
                        print(f"更新任务状态失败：{e}")
                        return False
            return False
    
    def get_task_statistics(self) -> dict:
        """获取任务统计信息"""
        tasks = self.load_tasks()
        total = len(tasks)
        completed = sum(1 for t in tasks if t['status'] == 'completed')
        failed = sum(1 for t in tasks if t['status'] == 'failed')
        pending = sum(1 for t in tasks if t['status'] == 'pending')
        running = sum(1 for t in tasks if t['status'] == 'running')
        
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'pending': pending,
            'running': running,
            'progress': round(completed / total * 100, 2) if total > 0 else 0
        }
