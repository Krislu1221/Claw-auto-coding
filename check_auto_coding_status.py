#!/usr/bin/env python3
"""
Auto-Coding 状态检查脚本

被 OpenClaw cron 调用，检查任务状态并输出决策 JSON。

用法：
    python check_auto_coding_status.py <project_dir> [--task-id xxx]

输出 JSON：
    {
        "status": "completed|failed|rejected|timeout|approval_required|running|unknown",
        "task_id": "ac-xxxx",
        "project_dir": "/path/to/project",
        "current_phase": "implementation",
        "completed_phases": ["analyze", "research"],
        "elapsed_minutes": 12.5,
        "should_notify": true,
        "should_delete_cron": false,
        "message_type": "progress|completion|approval|failure",
        "message": "任务完成，耗时 12.5 分钟..."
    }

退出码：
    0: 正常输出
    1: 错误
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime


def load_state(project_dir: Path) -> dict:
    """加载 state.json"""
    state_file = project_dir / ".auto-coding" / "state.json"
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {}


def load_pending_approval(project_dir: Path) -> dict:
    """加载 pending_approval.json"""
    pending_file = project_dir / ".auto-coding" / "pending_approval.json"
    if not pending_file.exists():
        return {}
    try:
        with open(pending_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {}


def format_duration(created_at: str) -> str:
    """格式化时长"""
    try:
        start = datetime.fromisoformat(created_at)
        elapsed = datetime.now() - start
        minutes = elapsed.total_seconds() / 60
        if minutes < 1:
            return f"{elapsed.seconds} 秒"
        elif minutes < 60:
            return f"{minutes:.1f} 分钟"
        else:
            hours = minutes / 60
            return f"{hours:.1f} 小时"
    except (ValueError, TypeError):
        return "未知"


def build_message(state: dict, pending: dict) -> dict:
    """
    根据状态构建决策
    
    Returns:
        {
            status: 状态码
            should_notify: 是否发通知
            should_delete_cron: 是否删 cron
            message_type: 消息类型
            message: 消息内容
        }
    """
    phase = state.get("current_phase", "unknown")
    task_id = state.get("task_id", "unknown")
    requirements = state.get("requirements", "")[:80]
    completed = state.get("completed_phases", [])
    created_at = state.get("created_at", "")
    duration = format_duration(created_at)

    # 终态判断
    final_phases = {"completed", "failed", "rejected", "timeout"}

    if phase in final_phases:
        # 终态
        status_map = {
            "completed": ("完成", "✅"),
            "failed": ("失败", "❌"),
            "rejected": ("终止", "🛑"),
            "timeout": ("超时", "⏱️"),
        }
        label, emoji = status_map.get(phase, ("结束", "📋"))

        return {
            "status": phase,
            "should_notify": True,
            "should_delete_cron": True,
            "message_type": "completion" if phase == "completed" else "failure",
            "message": (
                f"【Auto-Coding {label}】{emoji}\n"
                f"任务：{task_id}\n"
                f"需求：{requirements}...\n"
                f"耗时：{duration}\n"
                f"完成阶段：{' → '.join(completed) if completed else '无'}\n"
                f"项目：{state.get('project_dir', '')}"
            ),
        }

    if phase.startswith("approval_required"):
        # 需要审批
        pending_info = load_pending_approval(Path(state.get("project_dir", ".")))
        approval_id = pending_info.get("approval_id", "unknown")
        operation = pending_info.get("operation", "未知操作")

        return {
            "status": "approval_required",
            "should_notify": True,
            "should_delete_cron": False,
            "message_type": "approval",
            "message": (
                f"【Auto-Coding 审批】⏸️\n"
                f"任务：{task_id}\n"
                f"操作：{operation}\n"
                f"耗时：{duration}\n"
                f"完成阶段：{' → '.join(completed) if completed else '无'}\n"
                f"\n"
                f"回复格式：确认 {approval_id}  /  终止 {approval_id}\n"
                f"项目：{state.get('project_dir', '')}"
            ),
        }

    # 还在运行
    return {
        "status": "running",
        "should_notify": False,
        "should_delete_cron": False,
        "message_type": "progress",
        "message": (
            f"任务 {task_id} 进行中\n"
            f"当前阶段：{phase}\n"
            f"已耗时：{duration}\n"
            f"完成阶段：{' → '.join(completed) if completed else '无'}"
        ),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "缺少 project_dir 参数",
            "usage": "python check_auto_coding_status.py <project_dir> [--task-id xxx]",
        }, ensure_ascii=False))
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    task_id = None
    if "--task-id" in sys.argv:
        idx = sys.argv.index("--task-id")
        if idx + 1 < len(sys.argv):
            task_id = sys.argv[idx + 1]

    # 加载状态
    state = load_state(project_dir)
    pending = load_pending_approval(project_dir)

    if not state:
        print(json.dumps({
            "status": "unknown",
            "project_dir": str(project_dir),
            "task_id": task_id,
            "should_notify": False,
            "should_delete_cron": False,
            "message_type": "error",
            "message": f"未找到状态文件：{project_dir / '.auto-coding/state.json'}",
        }, ensure_ascii=False))
        sys.exit(0)

    # 强制 task_id 一致
    if task_id and state.get("task_id") != task_id:
        print(json.dumps({
            "status": "unknown",
            "project_dir": str(project_dir),
            "task_id": task_id,
            "should_notify": False,
            "should_delete_cron": False,
            "message_type": "error",
            "message": f"任务 ID 不匹配：期望 {task_id}，实际 {state.get('task_id')}",
        }, ensure_ascii=False))
        sys.exit(0)

    # 构建决策
    decision = build_message(state, pending)
    decision["task_id"] = state.get("task_id", task_id)
    decision["project_dir"] = str(project_dir)
    decision["current_phase"] = state.get("current_phase", "unknown")
    decision["completed_phases"] = state.get("completed_phases", [])

    # 输出 JSON
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
