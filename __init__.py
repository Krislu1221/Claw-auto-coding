"""
Auto-Coding Skill - 智能自主编码系统
Auto-Coding Skill - Intelligent Autonomous Coding System

通过多角色 Soul + 多模型切换完成从需求到代码的完整开发流程。

Usage:
    # Python 模块调用
    from auto_coding_workflow import AutoCodingWorkflow
    
    workflow = AutoCodingWorkflow(
        requirements="创建一个 Todo 应用",
        timeout_minutes=30
    )
    result = await workflow.run()

Version:
    v3.7.0-discipline - 工程纪律系统（SkillInjector + ScorecardEngine + 审计追踪 + 子 Agent 问责）
"""

__version__ = "3.7.0-discipline"
__all__ = [
    "AutoCodingWorkflow",
    "AutoCodingWorkflowEnhanced",
    "DependencyManager",
    "AgentSoulLoader",
    "ModelSelector",
    "TaskManager",
    "ReviewerWorker",
    "ComplexityAnalyzer",
]

# 核心模块导出
from .auto_coding_workflow import AutoCodingWorkflow
from .workflow_enhanced import AutoCodingWorkflowEnhanced
from .dependency_manager import DependencyManager
from .agent_soul_loader import AgentSoulLoader
from .model_selector import ModelSelector
from .task_manager import TaskManager
from .workers.reviewer_worker import ReviewerWorker
from .complexity_analyzer import ComplexityAnalyzer
