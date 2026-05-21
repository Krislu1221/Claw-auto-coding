#!/usr/bin/env python3
"""
WorkflowConfig - 工作流配置解析器

从 .auto-coding/workflow.yaml 读取项目级工作流配置，
替代硬编码在 SKILL.md 中的阶段和 Agent 分配。
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class PhaseConfig:
    """阶段配置
    
    v3.4.1: model 可为 None，由工作流初始化时通过 ModelSelector 按 role 动态分配
    """
    id: str
    agent: str
    role: str  # v3.4.1: 角色，用于 ModelSelector 动态选模型（engineering/testing/reviewer 等）
    model: Optional[str] = None  # v3.4.1: None = 动态分配
    description: str = ""
    prompt: str = ""
    enabled: bool = True
    skippable: bool = False
    # 审批门控：满足条件时暂停等人工确认
    gates: List[Dict[str, Any]] = field(default_factory=list)
    # 超时配置（秒）
    timeout_seconds: int = 300
    # 重试次数
    retry_count: int = 3


@dataclass
class WorkflowConfig:
    """工作流全局配置"""
    name: str = "default"
    version: str = "1.0"
    description: str = ""
    # 阶段定义（有序）
    phases: List[PhaseConfig] = field(default_factory=list)
    # 迭代配置（编码→测试→反思→优化循环）
    max_iterations: int = 3
    # 复杂度分级路由
    complexity_routing: Dict[str, List[str]] = field(default_factory=dict)
    # 全局模型映射（Agent → 模型）
    agent_models: Dict[str, str] = field(default_factory=dict)
    # 全局约束
    constraints: Dict[str, Any] = field(default_factory=dict)


DEFAULT_WORKFLOW = WorkflowConfig(
    name="auto-coding-default",
    description="Auto-Coding v3.4.1 默认工作流（模型由 ModelSelector 动态分配 + 5项嵌入式工程技能）",
    phases=[
        PhaseConfig(
            id="design",
            agent="engineering-software-architect",
            role="engineering",  # v3.4.1: 只声明角色，模型由 ModelSelector 动态分配
            description="技术方案设计",
            prompt="分析需求并设计技术方案，包括：技术栈选型、架构设计、目录结构。先陈述问题和约束，再提出方案。",
        ),
        PhaseConfig(
            id="decomposition",
            agent="engineering-software-architect",
            role="engineering",
            description="任务拆解和依赖管理",
            prompt="根据技术方案拆解任务，定义任务依赖关系。识别核心需求和边界条件。",
        ),
        PhaseConfig(
            id="coding",
            agent="engineering-senior-developer",
            role="engineering",
            description="代码实现",
            prompt="按 Karpathy 铁律生成代码：极简、手术刀修改、不添加未请求功能。类型注解、异常处理、性能意识。",
            gates=[
                {"type": "path-check", "condition": "touches config/ or .env", "action": "require-approval"},
            ],
        ),
        PhaseConfig(
            id="testing",
            agent="testing-api-tester",
            role="testing",
            description="功能测试",
            prompt="编写测试用例并验证功能正确性。精确到字段，给出具体断言。",
        ),
        PhaseConfig(
            id="reflection",
            agent="engineering-code-reviewer",
            role="reviewer",
            description="代码审查",
            prompt="审查代码：1) 是否符合需求 2) 是否有额外内容 3) 是否过度设计。分级标注：🔴阻塞项 🟡建议项 💭小改进",
        ),
        PhaseConfig(
            id="optimization",
            agent="engineering-optimizer",
            role="engineering",
            description="代码优化和重构",
            prompt="根据审查结果进行深度优化：优雅优先、性能敏感、消除冗余。给出优化后代码 + 逐条说明优化点及收益。",
        ),
        PhaseConfig(
            id="verification",
            agent="testing-verifier",
            role="testing",
            description="交付验证",
            prompt="最终交付验证：功能完整性、边界覆盖、集成正确性、文档完整。逐条验证项 + 通过/不通过 + 具体证据。",
        ),
    ],
    max_iterations=3,
    complexity_routing={
        "A": ["coding", "testing", "verification"],
        "B": ["design", "coding", "testing", "verification"],
        "C": ["design", "decomposition", "coding", "testing", "reflection", "optimization", "verification"],
    },
    # v3.4.1: agent_models 仅用于用户自定义覆盖，默认情况下不使用
    # 所有模型由 ModelSelector 按 role 动态分配
    agent_models={},
    constraints={
        "must_preserve": [],
        "no_modify_patterns": [],
        "style_guide": None,
    },
)


class WorkflowConfigLoader:
    """
    工作流配置加载器
    
    加载顺序（优先级从高到低）：
    1. 项目目录 .auto-coding/workflow.yaml
    2. 默认配置（DEFAULT_WORKFLOW）
    """

    def __init__(self, project_dir: Path, model_selector=None):
        self.project_dir = Path(project_dir)
        self.config_dir = self.project_dir / ".auto-coding"
        self.config_file = self.config_dir / "workflow.yaml"
        # v3.4.1: ModelSelector 用于为 role 动态分配模型
        if model_selector is None:
            from model_selector import get_model_selector
            self.model_selector = get_model_selector()
        else:
            self.model_selector = model_selector

    def load(self) -> WorkflowConfig:
        """加载配置，项目配置不存在则返回默认
        
        v3.4.1: 对 model=None 的阶段，通过 ModelSelector 按 role 动态分配模型
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                config = self._parse(data)
            except (yaml.YAMLError, KeyError) as e:
                print(f"⚠️  workflow.yaml 解析失败：{e}，使用默认配置")
                config = DEFAULT_WORKFLOW
        else:
            # 返回默认配置的同时，写入模板供用户参考
            self._write_default_template()
            config = DEFAULT_WORKFLOW
        
        # v3.4.1: 动态分配模型（model=None 的阶段）
        self._resolve_models(config)
        return config
    
    def _resolve_models(self, config: WorkflowConfig) -> None:
        """为 model=None 的阶段动态分配模型
        
        v3.4.1: 统一走 ModelSelector 降级链路，不允许硬编码兜底
        """
        for phase in config.phases:
            if phase.model is None or phase.model == "":
                # 通过 ModelSelector 按角色分配模型
                selected_model = self.model_selector.select_model_for_role(phase.role)
                if not selected_model:
                    raise RuntimeError(
                        f"❌ 阶段 '{phase.id}' (role={phase.role}) 无可用模型。\n"
                        f"请配置至少一个 provider，或检查 ModelSelector 降级链路。"
                    )
                phase.model = selected_model
                print(f"   🎯 阶段 '{phase.id}' 动态分配模型: {selected_model}")

    def _parse(self, data: Dict[str, Any]) -> WorkflowConfig:
        """解析 YAML 数据为 WorkflowConfig"""
        phases = []
        for p in data.get("phases", []):
            phases.append(PhaseConfig(
                id=p["id"],
                agent=p["agent"],
                role=p.get("role", "engineering"),  # v3.4.1: 默认 engineering 角色
                model=p.get("model"),  # v3.4.1: None = 动态分配
                description=p.get("description", ""),
                prompt=p.get("prompt", ""),
                enabled=p.get("enabled", True),
                skippable=p.get("skippable", False),
                gates=p.get("gates", []),
                timeout_seconds=p.get("timeout_seconds", 300),
                retry_count=p.get("retry_count", 3),
            ))
        
        return WorkflowConfig(
            name=data.get("name", "custom"),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            phases=phases,
            max_iterations=data.get("max_iterations", 3),
            complexity_routing=data.get("complexity_routing", DEFAULT_WORKFLOW.complexity_routing),
            agent_models=data.get("agent_models", DEFAULT_WORKFLOW.agent_models),
            constraints=data.get("constraints", {}),
        )

    def _write_default_template(self):
        """写入默认配置模板到项目目录"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        template = self._generate_template()
        template_file = self.config_dir / "workflow.yaml.template"
        with open(template_file, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"📄 已生成 workflow.yaml.template：{template_file}")
        print(f"   如需自定义，复制为 workflow.yaml 后修改")

    def _generate_template(self) -> str:
        """生成模板内容"""
        return '''# Auto-Coding 工作流配置
# 复制此文件为 workflow.yaml 后即可自定义

name: my-project-workflow
version: "1.0"
description: 自定义 Auto-Coding 工作流

# 阶段定义（按顺序执行）
phases:
  - id: analyze
    agent: AutoAnalyzer
    model: deepseek/deepseek-v4-pro
    description: 需求分析
    prompt: 分析需求复杂度，确认边界条件

  - id: research
    agent: Coordinator
    model: xiaomimimo/mimo-v2.5-pro
    description: 技术调研
    prompt: 拆解需求，识别技术依赖

  - id: synthesis
    agent: Coordinator
    model: xiaomimimo/mimo-v2.5-pro
    description: 架构设计
    prompt: 设计最小可行架构
    skippable: true  # A/B 级任务可跳过

  - id: implementation
    agent: EngineeringWorker
    model: xiaomimimo/mimo-v2.5-pro
    description: 代码实现
    prompt: 按 Karpathy 铁律生成代码
    gates:
      # 如果修改了 config/ 或 .env，需要人工审批
      - type: path-check
        condition: "touches config/ or .env"
        action: require-approval

  - id: review
    agent: ReviewerWorker
    model: deepseek/deepseek-v4-pro
    description: 代码审查
    prompt: 审查代码质量和过度设计

  - id: verification
    agent: TestingWorker
    model: xiaomimimo/mimo-v2.5
    description: 测试验证
    prompt: 运行测试，验证功能

# 迭代循环配置（implementation → review → verification）
max_iterations: 3

# 复杂度分级路由
# A: 单函数/Bug 修复
# B: 模块开发/新功能
# C: 完整系统/架构重构
complexity_routing:
  A: [implementation, review, verification]
  B: [research, implementation, review, verification]
  C: [analyze, research, synthesis, implementation, review, verification]

# Agent 默认模型映射
agent_models:
  Coordinator: xiaomimimo/mimo-v2.5-pro
  EngineeringWorker: xiaomimimo/mimo-v2.5-pro
  ReviewerWorker: deepseek/deepseek-v4-pro
  TestingWorker: xiaomimimo/mimo-v2.5
  AutoAnalyzer: deepseek/deepseek-v4-pro
'''

    def get_phases_for_complexity(self, complexity: str) -> List[PhaseConfig]:
        """根据复杂度获取阶段列表"""
        config = self.load()
        phase_ids = config.complexity_routing.get(complexity, config.complexity_routing.get("B", []))
        phase_map = {p.id: p for p in config.phases}
        return [phase_map[pid] for pid in phase_ids if pid in phase_map]
