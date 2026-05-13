#!/usr/bin/env python3
"""
ApprovalRules - 审批规则引擎

基于 .auto-coding/rules.yaml 配置，对文件操作进行自动审批或人工审批决策。
"""

import yaml
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ApprovalDecision:
    """审批决策结果"""
    approved: bool          # 是否通过
    requires_human: bool    # 是否需要人工确认
    reason: str = ""        # 决策理由
    operation: str = ""     # 操作类型
    files: List[str] = field(default_factory=list)


@dataclass
class RuleSet:
    """规则集合"""
    auto_approve_edit: List[str] = field(default_factory=list)
    auto_approve_run: List[str] = field(default_factory=list)
    auto_approve_create: List[str] = field(default_factory=list)
    require_approval_edit: List[str] = field(default_factory=list)
    require_approval_delete: List[str] = field(default_factory=list)
    require_approval_run: List[str] = field(default_factory=list)
    notify_on_complete: bool = True


DEFAULT_RULES = RuleSet(
    auto_approve_edit=["src/*", "test/*", "tests/*", "docs/*", "*.md", "*.html", "*.css", "*.js", "*.py", "*.json"],
    auto_approve_run=["npm test", "npm run test", "pytest", "python -m pytest", "npm run build"],
    auto_approve_create=["src/*", "test/*", "docs/*"],
    require_approval_edit=["config/*", ".env*", "*.config.js", "*.config.ts", ".github/*"],
    require_approval_delete=["*"],  # 删除任何文件都需要审批
    require_approval_run=["git push", "npm publish", "docker push", "rm -rf", "curl *|sh"],
    notify_on_complete=True,
)


class ApprovalRulesEngine:
    """
    审批规则引擎
    
    加载顺序：
    1. 项目目录 .auto-coding/rules.yaml
    2. 默认规则（DEFAULT_RULES）
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.rules_dir = self.project_dir / ".auto-coding"
        self.rules_file = self.rules_dir / "rules.yaml"
        self._rules: Optional[RuleSet] = None

    def _load_rules(self) -> RuleSet:
        """加载规则配置"""
        if self._rules:
            return self._rules
        
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._rules = self._parse_rules(data)
                return self._rules
            except Exception as e:
                print(f"⚠️  rules.yaml 解析失败：{e}，使用默认规则")
        
        self._rules = DEFAULT_RULES
        self._write_default_template()
        return self._rules

    def _parse_rules(self, data: Dict[str, Any]) -> RuleSet:
        """解析规则数据"""
        auto = data.get("auto_approve", {})
        req = data.get("require_approval", {})
        return RuleSet(
            auto_approve_edit=auto.get("edit", DEFAULT_RULES.auto_approve_edit),
            auto_approve_run=auto.get("run", DEFAULT_RULES.auto_approve_run),
            auto_approve_create=auto.get("create", DEFAULT_RULES.auto_approve_create),
            require_approval_edit=req.get("edit", DEFAULT_RULES.require_approval_edit),
            require_approval_delete=req.get("delete", DEFAULT_RULES.require_approval_delete),
            require_approval_run=req.get("run", DEFAULT_RULES.require_approval_run),
            notify_on_complete=data.get("notify_on_complete", True),
        )

    def _write_default_template(self):
        """写入默认规则模板"""
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        template = '''# Auto-Coding 审批规则配置
# 复制此文件为 rules.yaml 后即可自定义

# 自动通过的操作（不需要人工确认）
auto_approve:
  # 修改这些路径的文件自动通过
  edit:
    - "src/*"
    - "test/*"
    - "tests/*"
    - "docs/*"
    - "*.md"
    - "*.html"
    - "*.css"
    - "*.js"
    - "*.py"
    - "*.json"
  # 运行这些命令自动通过
  run:
    - "npm test"
    - "pytest"
    - "python -m pytest"
    - "npm run build"
  # 在这些路径创建文件自动通过
  create:
    - "src/*"
    - "test/*"
    - "docs/*"

# 需要人工审批的操作
require_approval:
  # 修改这些路径需要确认
  edit:
    - "config/*"
    - ".env*"
    - "*.config.js"
    - ".github/*"
  # 删除任何文件都需要确认（* 表示全部）
  delete:
    - "*"
  # 运行这些命令需要确认
  run:
    - "git push"
    - "npm publish"
    - "rm -rf"

# 任务完成时是否发送通知
notify_on_complete: true
'''
        template_file = self.rules_dir / "rules.yaml.template"
        with open(template_file, "w", encoding="utf-8") as f:
            f.write(template)

    def check_edit(self, file_paths: List[str]) -> ApprovalDecision:
        """检查文件修改操作"""
        rules = self._load_rules()
        
        # 先检查是否需要审批
        for path in file_paths:
            for pattern in rules.require_approval_edit:
                if fnmatch.fnmatch(path, pattern):
                    return ApprovalDecision(
                        approved=False,
                        requires_human=True,
                        reason=f"文件 {path} 匹配审批规则 '{pattern}'",
                        operation="edit",
                        files=file_paths,
                    )
        
        # 再检查是否自动通过
        for path in file_paths:
            matched = False
            for pattern in rules.auto_approve_edit:
                if fnmatch.fnmatch(path, pattern):
                    matched = True
                    break
            if not matched:
                # 不在白名单也不在黑名单 → 默认需要审批（安全优先）
                return ApprovalDecision(
                    approved=False,
                    requires_human=True,
                    reason=f"文件 {path} 不在自动通过列表中",
                    operation="edit",
                    files=file_paths,
                )
        
        return ApprovalDecision(
            approved=True,
            requires_human=False,
            reason="所有文件均在自动通过列表中",
            operation="edit",
            files=file_paths,
        )

    def check_delete(self, file_paths: List[str]) -> ApprovalDecision:
        """检查文件删除操作"""
        rules = self._load_rules()
        
        # 删除默认需要审批（除非特别配置）
        delete_rules = rules.require_approval_delete
        if "*" in delete_rules:
            return ApprovalDecision(
                approved=False,
                requires_human=True,
                reason="删除操作需要人工确认",
                operation="delete",
                files=file_paths,
            )
        
        for path in file_paths:
            for pattern in delete_rules:
                if fnmatch.fnmatch(path, pattern):
                    return ApprovalDecision(
                        approved=False,
                        requires_human=True,
                        reason=f"文件 {path} 匹配删除审批规则",
                        operation="delete",
                        files=file_paths,
                    )
        
        return ApprovalDecision(
            approved=True,
            requires_human=False,
            reason="删除文件不在审批列表中",
            operation="delete",
            files=file_paths,
        )

    def check_run(self, command: str) -> ApprovalDecision:
        """检查命令执行"""
        rules = self._load_rules()
        
        # 先检查是否需要审批
        for pattern in rules.require_approval_run:
            if fnmatch.fnmatch(command, pattern):
                return ApprovalDecision(
                    approved=False,
                    requires_human=True,
                    reason=f"命令 '{command}' 匹配审批规则 '{pattern}'",
                    operation="run",
                    files=[],
                )
        
        # 再检查是否自动通过
        for pattern in rules.auto_approve_run:
            if fnmatch.fnmatch(command, pattern):
                return ApprovalDecision(
                    approved=True,
                    requires_human=False,
                    reason=f"命令 '{command}' 在自动通过列表中",
                    operation="run",
                    files=[],
                )
        
        # 不在白名单也不在黑名单 → 默认需要审批
        return ApprovalDecision(
            approved=False,
            requires_human=True,
            reason=f"命令 '{command}' 不在自动通过列表中",
            operation="run",
            files=[],
        )

    def should_notify_on_complete(self) -> bool:
        """任务完成时是否需要通知"""
        rules = self._load_rules()
        return rules.notify_on_complete
