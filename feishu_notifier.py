#!/usr/bin/env python3
"""
FeishuNotifier - Auto-Coding 飞书通知模块

负责：
1. 审批通知：检测到敏感操作时发飞书消息
2. 完成通知：任务完成后发汇总报告
3. 审批回复解析：从用户回复中提取审批决定

使用方式：
    from feishu_notifier import FeishuNotifier
    notifier = FeishuNotifier()
    notifier.send_approval_request(task_id, operation, files, project_dir)
    # 用户回复后：
    decision = notifier.parse_approval_reply(user_text)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


class FeishuNotifier:
    """
    飞书通知器
    
    与 workflow_enhanced.py 配合：
    - 审批点：发飞书消息给用户
    - 完成时：发任务报告
    - 解析回复：把用户消息转成审批决策
    """

    def __init__(self, state_dir: Optional[Path] = None):
        """
        Args:
            state_dir: 状态目录，用于存 pending_approval 标志
        """
        self.state_dir = Path(state_dir) if state_dir else None

    # ========================================================================
    # 发送通知
    # ========================================================================

    def send_approval_request(self, task_id: str, operation: str,
                               files: List[str], project_dir: Path,
                               reason: str = "") -> str:
        """
        发送审批请求到飞书
        
        Returns:
            approval_id: 审批请求 ID
        """
        approval_id = f"aprv-{task_id}"

        # 构建消息文本
        msg = self._build_approval_message(
            task_id=task_id,
            approval_id=approval_id,
            operation=operation,
            files=files,
            project_dir=project_dir,
            reason=reason,
        )

        # 保存 pending approval 标志（用于恢复时检测）
        if self.state_dir:
            self._save_pending_approval(approval_id, task_id, operation, files)

        # 返回消息内容和 approval_id
        # 注意：实际发送由外层调用 message tool
        return msg

    def send_completion_report(self, task_id: str, project_dir: Path,
                                elapsed_minutes: float,
                                completed_phases: List[str],
                                requirements: str,
                                test_passed: bool = False) -> str:
        """发送任务完成报告"""
        status_emoji = "✅" if test_passed else "⚠️"
        msg = (
            f"【Auto-Coding 完成】{status_emoji}\n"
            f"任务：{task_id}\n"
            f"需求：{requirements[:60]}...\n"
            f"耗时：{elapsed_minutes:.1f} 分钟\n"
            f"完成阶段：{' → '.join(completed_phases)}\n"
            f"项目：{project_dir}\n"
        )
        return msg

    def _build_approval_message(self, task_id: str, approval_id: str,
                                 operation: str, files: List[str],
                                 project_dir: Path, reason: str = "") -> str:
        """构建审批消息文本"""
        lines = [
            "【Auto-Coding 审批】⏸️",
            "",
            f"任务：{task_id}",
            f"操作：{operation}",
        ]
        if reason:
            lines.append(f"原因：{reason}")
        if files:
            lines.append(f"涉及文件：{', '.join(files)}")
        lines.append(f"项目：{project_dir}")
        lines.append("")
        lines.append(f"回复格式：确认 {approval_id}  /  终止 {approval_id}")
        lines.append("（不回复则任务暂停，可随时处理）")

        return "\n".join(lines)

    # ========================================================================
    # 解析审批回复
    # ========================================================================

    def parse_approval_reply(self, user_text: str) -> Optional[Dict[str, Any]]:
        """
        解析用户回复是否为审批决定
        
        支持的格式：
        - "确认 aprv-xxx" / "确认" → approved
        - "终止 aprv-xxx" / "终止" / "停止" → rejected
        - "跳过 aprv-xxx" / "跳过" → skipped
        
        Returns:
            None: 不是审批回复
            dict: {"approval_id": str, "decision": "approved|rejected|skipped"}
        """
        text = user_text.strip().lower()

        # 匹配 "确认 [approval_id]"
        confirm_patterns = [r'^确认\s*(\S+)?', r'^approve\s*(\S+)?', r'^yes\s*(\S+)?', r'^y\s*$']
        for pattern in confirm_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                approval_id = match.group(1) if match.group(1) else self._find_pending_approval()
                if approval_id:
                    return {"approval_id": approval_id, "decision": "approved"}

        # 匹配 "终止 [approval_id]"
        reject_patterns = [r'^终止\s*(\S+)?', r'^停止\s*(\S+)?', r'^reject\s*(\S+)?', r'^no\s*(\S+)?', r'^n\s*$']
        for pattern in reject_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                approval_id = match.group(1) if match.group(1) else self._find_pending_approval()
                if approval_id:
                    return {"approval_id": approval_id, "decision": "rejected"}

        # 匹配 "跳过 [approval_id]"
        skip_patterns = [r'^跳过\s*(\S+)?', r'^skip\s*(\S+)?']
        for pattern in skip_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                approval_id = match.group(1) if match.group(1) else self._find_pending_approval()
                if approval_id:
                    return {"approval_id": approval_id, "decision": "skipped"}

        return None

    # ========================================================================
    # 状态管理（pending approval）
    # ========================================================================

    def _save_pending_approval(self, approval_id: str, task_id: str,
                                operation: str, files: List[str]):
        """保存 pending approval 到文件"""
        if not self.state_dir:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        pending_file = self.state_dir / "pending_approval.json"
        data = {
            "approval_id": approval_id,
            "task_id": task_id,
            "operation": operation,
            "files": files,
            "created_at": __import__('datetime').datetime.now().isoformat(),
            "status": "pending",
        }
        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _find_pending_approval(self) -> Optional[str]:
        """查找当前 pending 的 approval_id"""
        if not self.state_dir:
            return None
        pending_file = self.state_dir / "pending_approval.json"
        if not pending_file.exists():
            return None
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status") == "pending":
                return data.get("approval_id")
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def resolve_pending_approval(self, approval_id: str, decision: str):
        """标记 pending approval 为已处理"""
        if not self.state_dir:
            return
        pending_file = self.state_dir / "pending_approval.json"
        if pending_file.exists():
            try:
                with open(pending_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("approval_id") == approval_id:
                    data["status"] = decision
                    data["resolved_at"] = __import__('datetime').datetime.now().isoformat()
                    with open(pending_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, KeyError):
                pass

    def has_pending_approval(self) -> bool:
        """检查是否有未处理的审批"""
        return self._find_pending_approval() is not None

    def get_pending_approval_info(self) -> Optional[Dict[str, Any]]:
        """获取 pending approval 的详细信息"""
        if not self.state_dir:
            return None
        pending_file = self.state_dir / "pending_approval.json"
        if not pending_file.exists():
            return None
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status") == "pending":
                return data
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def clear_pending_approval(self):
        """清除 pending approval"""
        if not self.state_dir:
            return
        pending_file = self.state_dir / "pending_approval.json"
        if pending_file.exists():
            pending_file.unlink()
