#!/usr/bin/env python3
"""
StateManager - Auto-Coding 状态持久化管理器

替代 ~/.hermes/projects/{project_name}/status/，改为项目内 .auto-coding/state.json
支持断点续传、跨 session 恢复。
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TaskState:
    """单个任务的状态"""
    task_id: str
    phase: str                          # 当前阶段
    status: str = "pending"             # pending/running/completed/failed/approval_required
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    start_time: str = ""
    end_time: str = ""
    model_used: str = ""
    tokens_used: int = 0


@dataclass
class WorkflowState:
    """工作流全局状态"""
    version: str = "3.6.2"
    task_id: str = ""
    requirements: str = ""
    current_phase: str = "idle"         # idle/design/decomposition/coding/testing/reflection/optimization/verification/output
    completed_phases: List[str] = field(default_factory=list)
    phase_states: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    test_passed: bool = False
    created_at: str = ""
    updated_at: str = ""
    approval_queue: List[Dict[str, Any]] = field(default_factory=list)
    agent_usage: Dict[str, Any] = field(default_factory=dict)
    # v3.6.2: Verifier 硬否决追踪
    veto_retry_count: int = 0
    veto_retry_max: int = 3
    veto_retry_history: List[Dict[str, Any]] = field(default_factory=list)
    # v3.6.2: 子 Agent recovery 信息
    failed_agents: List[Dict[str, Any]] = field(default_factory=list)
    agent_recovery_attempts: int = 0


class StateManager:
    """
    状态管理器
    
    负责：
    1. 读写 .auto-coding/state.json
    2. 阶段切换时自动落盘
    3. 任务恢复
    4. 审批队列管理
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.state_dir = self.project_dir / ".auto-coding"
        self.state_file = self.state_dir / "state.json"
        self.status_dir = self.state_dir / "status"  # 状态同步标记目录
        
        # 确保目录存在
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.status_dir.mkdir(parents=True, exist_ok=True)
    
    def init_state(self, requirements: str = "", task_id: str = None) -> WorkflowState:
        """初始化新任务状态"""
        now = datetime.now().isoformat()
        state = WorkflowState(
            task_id=task_id or f"ac-{uuid.uuid4().hex[:8]}",
            requirements=requirements,
            current_phase="idle",
            completed_phases=[],
            phase_states={},
            context={},
            results={
                "code": None,
                "test_result": None,
                "reflection": None,
                "fixed_code": None,
                "final_check": None,
                "iterations": 0,
                "passed": False,
                "task_progress": {},
                "agent_usage": {},
            },
            iterations=0,
            test_passed=False,
            created_at=now,
            updated_at=now,
            approval_queue=[],
            agent_usage={},
        )
        self._save(state)
        return state
    
    def load_state(self) -> Optional[WorkflowState]:
        """加载已有状态，不存在则返回 None"""
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._dict_to_state(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️  状态文件损坏：{e}，将创建新状态")
            return None
    
    def save_phase(self, state: WorkflowState, phase: str, phase_data: Dict[str, Any] = None):
        """保存阶段完成状态"""
        state.current_phase = phase
        if phase not in state.completed_phases:
            state.completed_phases.append(phase)
        if phase_data:
            state.phase_states[phase] = phase_data
        state.updated_at = datetime.now().isoformat()
        self._save(state)
    
    def save_progress(self, state: WorkflowState, **kwargs):
        """增量保存进度（不标记阶段完成）"""
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
            else:
                state.results[key] = value
        state.updated_at = datetime.now().isoformat()
        self._save(state)
    
    def push_approval(self, state: WorkflowState, operation: str, details: Dict[str, Any]) -> str:
        """
        推送审批请求到队列
        
        Returns:
            approval_id: 审批 ID
        """
        approval_id = f"aprv-{uuid.uuid4().hex[:6]}"
        approval_item = {
            "id": approval_id,
            "operation": operation,
            "details": details,
            "status": "pending",  # pending/approved/rejected/skipped
            "created_at": datetime.now().isoformat(),
            "resolved_at": None,
        }
        state.approval_queue.append(approval_item)
        state.current_phase = f"approval_required:{approval_id}"
        state.updated_at = datetime.now().isoformat()
        self._save(state)
        return approval_id
    
    def resolve_approval(self, state: WorkflowState, approval_id: str, decision: str) -> bool:
        """
        处理审批决定
        
        Args:
            decision: approved / rejected / skipped
        """
        for item in state.approval_queue:
            if item["id"] == approval_id and item["status"] == "pending":
                item["status"] = decision
                item["resolved_at"] = datetime.now().isoformat()
                state.updated_at = datetime.now().isoformat()
                self._save(state)
                return True
        return False
    
    def get_pending_approvals(self, state: WorkflowState) -> List[Dict[str, Any]]:
        """获取待审批列表"""
        return [a for a in state.approval_queue if a["status"] == "pending"]
    
    def can_resume(self) -> bool:
        """检查是否可以恢复任务"""
        state = self.load_state()
        if not state:
            return False
        # 如果所有阶段都完成了，不恢复
        if state.current_phase in ["output", "completed", "failed"]:
            return False
        # 如果有未处理的审批，不能自动恢复
        pending = self.get_pending_approvals(state)
        if pending:
            return False
        return True
    
    def get_resume_phase(self) -> Optional[str]:
        """获取应该从哪个阶段恢复"""
        state = self.load_state()
        if not state:
            return None
        
        # 如果当前阶段是 idle，从头开始
        if state.current_phase == "idle":
            return "design"
        
        # 如果当前阶段是审批状态，返回等待
        if state.current_phase.startswith("approval_required:"):
            return state.current_phase
        
        # 否则返回当前阶段（重新执行）
        return state.current_phase
    
    def reset_state(self):
        """重置状态（删除 state.json）"""
        if self.state_file.exists():
            self.state_file.unlink()
            print("🗑️  状态已重置")
    
    def _save(self, state: WorkflowState):
        """持久化到文件"""
        data = self._state_to_dict(state)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _state_to_dict(self, state: WorkflowState) -> Dict[str, Any]:
        """WorkflowState → dict"""
        return {
            "version": state.version,
            "task_id": state.task_id,
            "requirements": state.requirements,
            "current_phase": state.current_phase,
            "completed_phases": state.completed_phases,
            "phase_states": state.phase_states,
            "context": state.context,
            "results": state.results,
            "iterations": state.iterations,
            "test_passed": state.test_passed,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "approval_queue": state.approval_queue,
            "agent_usage": state.agent_usage,
            # v3.6.2: Verifier 否决追踪
            "veto_retry_count": state.veto_retry_count,
            "veto_retry_max": state.veto_retry_max,
            "veto_retry_history": state.veto_retry_history,
            # v3.6.2: 子 Agent recovery
            "failed_agents": state.failed_agents,
            "agent_recovery_attempts": state.agent_recovery_attempts,
        }
    
    def _dict_to_state(self, data: Dict[str, Any]) -> WorkflowState:
        """dict → WorkflowState"""
        return WorkflowState(
            version=data.get("version", "1.0"),
            task_id=data.get("task_id", ""),
            requirements=data.get("requirements", ""),
            current_phase=data.get("current_phase", "idle"),
            completed_phases=data.get("completed_phases", []),
            phase_states=data.get("phase_states", {}),
            context=data.get("context", {}),
            results=data.get("results", {}),
            iterations=data.get("iterations", 0),
            test_passed=data.get("test_passed", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            approval_queue=data.get("approval_queue", []),
            agent_usage=data.get("agent_usage", {}),
            # v3.6.2: Verifier 否决追踪
            veto_retry_count=data.get("veto_retry_count", 0),
            veto_retry_max=data.get("veto_retry_max", 3),
            veto_retry_history=data.get("veto_retry_history", []),
            # v3.6.2: 子 Agent recovery
            failed_agents=data.get("failed_agents", []),
            agent_recovery_attempts=data.get("agent_recovery_attempts", 0),
        )

    # ==================== 状态同步标记文件管理（双轨机制）====================
    # Worker 主动写标记，状态恢复时扫标记，无需高频轮询
    # 
    # 设计思路：
    #   旧方案：Cron 每 5 分钟跑一次 check_auto_coding_status.py
    #           → 每次都要启动 Python + 读状态文件
    #           → 多个任务就是多倍成本
    #           → 最差情况 5 分钟延迟
    #
    #   新方案：Worker 完成时写 .json 标记文件（0 Token 成本）
    #           状态恢复时扫一次所有标记
    #           → 和其他恢复逻辑合并，额外成本≈0
    #           → 理论上 0 延迟
    # ==========================================================================

    def mark_completed(self, state: WorkflowState, summary: str = ""):
        """任务完成，写完成标记（给状态同步使用）

        Worker 完成后主动调用，0 Token 成本
        """
        mark_file = self.status_dir / f"{state.task_id}-done.json"
        mark_data = {
            "task_id": state.task_id,
            "status": "completed",
            "current_phase": state.current_phase,
            "completed_phases": state.completed_phases,
            "requirements": state.requirements[:120],
            "summary": summary,
            "start_time": state.created_at,
            "completed_at": datetime.now().isoformat(),
            "project_dir": str(self.project_dir),
        }
        with open(mark_file, "w", encoding="utf-8") as f:
            json.dump(mark_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写完成标记：{mark_file.name}")

    def mark_running(self, state: WorkflowState, phase: str, message: str = ""):
        """写运行中标记（每个阶段开始时调用）
        
        Heartbeat 扫到这个标记，就知道任务还在跑，每 5 分钟通报一次进度。
        终态时这个文件会被 collector 自动删除。
        """
        mark_file = self.status_dir / f"{state.task_id}-running.json"
        mark_data = {
            "task_id": state.task_id,
            "status": "running",
            "current_phase": phase,
            "phase_message": message,
            "completed_phases": state.completed_phases,
            "start_time": state.created_at,
            "last_updated": datetime.now().isoformat(),
            "last_reported": None,  # Heartbeat 汇报后更新这个时间
            "project_dir": str(self.project_dir),
        }
        with open(mark_file, "w", encoding="utf-8") as f:
            json.dump(mark_data, f, ensure_ascii=False, indent=2)
    
    def mark_progress(self, state: WorkflowState, phase: str, message: str):
        """写进展标记（已废弃，改用 mark_running）"""
        # 向下兼容
        self.mark_running(state, phase, message)

    def mark_failed(self, state: WorkflowState, error: str):
        """任务失败标记"""
        mark_file = self.status_dir / f"{state.task_id}-failed.json"
        mark_data = {
            "task_id": state.task_id,
            "status": "failed",
            "error": error,
            "completed_phases": state.completed_phases,
            "start_time": state.created_at,
            "failed_at": datetime.now().isoformat(),
            "project_dir": str(self.project_dir),
        }
        with open(mark_file, "w", encoding="utf-8") as f:
            json.dump(mark_data, f, ensure_ascii=False, indent=2)
        print(f"❌ 已写失败标记：{mark_file.name}")

    def mark_approval_required(self, state: WorkflowState, approval_id: str, operation: str):
        """需要审批标记"""
        mark_file = self.status_dir / f"{state.task_id}-approval.json"
        mark_data = {
            "task_id": state.task_id,
            "status": "approval_required",
            "approval_id": approval_id,
            "operation": operation,
            "created_at": datetime.now().isoformat(),
            "project_dir": str(self.project_dir),
        }
        with open(mark_file, "w", encoding="utf-8") as f:
            json.dump(mark_data, f, ensure_ascii=False, indent=2)
        print(f"⏸️  已写审批标记：{mark_file.name}")

    # ==================== v3.6.2: 子 Agent recovery 支持 ====================

    def record_agent_failure(self, state: WorkflowState, agent_id: str, phase: str, error: str):
        """
        记录子 Agent 失败，供 recovery 决策使用
        
        Args:
            agent_id: 子 Agent 标识
            phase: 失败时的阶段ID
            error: 错误描述
        """
        failure = {
            "agent": agent_id,
            "phase": phase,
            "error": error[:200],
            "failed_at": datetime.now().isoformat(),
            "recovery_attempt": state.agent_recovery_attempts,
        }
        state.failed_agents.append(failure)
        state.agent_recovery_attempts += 1
        self._save(state)
        print(f"   📝 子 Agent 失败已记录: {agent_id} ({phase})")

    def has_recovery_budget(self, state: WorkflowState) -> bool:
        """检查是否还有 recovery 预算（最多 3 次全局 recovery）"""
        return state.agent_recovery_attempts < 3

    def get_recovery_action(self, state: WorkflowState, phase: str) -> str:
        """
        根据失败记录决定 recovery 策略
        
        Returns:
            'retry': 重试（同模型同 Worker）
            'fallback': 降级（换 fallback 模型）
            'escalate': 升级给人类审批
        """
        phase_failures = [f for f in state.failed_agents if f.get('phase') == phase]
        fail_count = len(phase_failures)
        
        if fail_count == 0:
            return 'retry'
        elif fail_count <= 2:
            return 'fallback'
        else:
            return 'escalate'

    def clear_phase_failures(self, state: WorkflowState, phase: str):
        """阶段成功后清理该阶段的失败记录"""
        state.failed_agents = [f for f in state.failed_agents if f.get('phase') != phase]
        self._save(state)


