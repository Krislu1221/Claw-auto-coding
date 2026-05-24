#!/usr/bin/env python3
"""
Auto-Coding Workflow Enhanced (v3.7.4)

基于 AutoCodingWorkflow (v3.2) 增强：
1. 状态持久化（.auto-coding/state.json）
2. 流程配置化（.auto-coding/workflow.yaml）
3. 审批策略（.auto-coding/rules.yaml）

使用方式：
    from workflow_enhanced import AutoCodingWorkflowEnhanced
    workflow = AutoCodingWorkflowEnhanced(
        requirements="实现一个用户登录功能",
        project_dir="./my-project"
    )
    await workflow.run()
"""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# 复用 v3.2 的依赖管理、模型选择、Agent Soul
from dependency_manager import DependencyManager
from model_selector import ModelSelector
from agent_soul_loader import AgentSoulLoader

# 新增组件
from state_manager import StateManager, WorkflowState
from workflow_config import WorkflowConfigLoader, PhaseConfig, DEFAULT_WORKFLOW
from approval_rules import ApprovalRulesEngine, ApprovalDecision
from feishu_notifier import FeishuNotifier

# v3.3 新增：ReviewerWorker 否决权 + ComplexityAnalyzer 自动分级
from workers.reviewer_worker import ReviewerWorker, ReviewResult
from complexity_analyzer import ComplexityAnalyzer, analyze_complexity

# 尝试导入现有工作流基类
try:
    from auto_coding_workflow import AutoCodingWorkflow, DesignOutput, CodingOutput, TestOutput, ReflectionOutput
    BASE_CLASS = AutoCodingWorkflow
except ImportError:
    BASE_CLASS = object
    print("⚠️  无法导入 AutoCodingWorkflow，将以独立模式运行")


class AutoCodingWorkflowEnhanced:
    """
    增强版 Auto-Coding 工作流
    
    核心增强：
    - 项目级配置：.auto-coding/workflow.yaml
    - 状态持久化：.auto-coding/state.json
    - 审批策略：.auto-coding/rules.yaml
    - 断点续传：session 中断后可从上次阶段恢复
    """

    def __init__(self, requirements: str, project_dir: str = None,
                 timeout_minutes: int = 30, user_models: List[Dict] = None,
                 acceptance_criteria: List[str] = None, constraints: Dict = None,
                 task_id: str = None, resume: bool = True):
        """
        Args:
            requirements: 需求描述
            project_dir: 项目目录（必须，用于存储 .auto-coding/ 配置和状态）
            timeout_minutes: 超时限制
            user_models: 用户自定义模型列表
            acceptance_criteria: 验收标准
            constraints: 约束条件
            task_id: 任务 ID（可选，默认自动生成）
            resume: 是否尝试恢复已有任务（默认 True）
        """
        self.requirements = requirements
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.timeout_minutes = timeout_minutes
        self.user_models = user_models or []
        self.acceptance_criteria = acceptance_criteria or ['功能可以正常运行', '代码无语法错误']
        self.constraints = constraints or {}
        self.task_id = task_id
        self.resume_enabled = resume

        # === 复用 v3.2 组件 ===
        # v3.4.1: 必须先创建 model_selector，传给 WorkflowConfigLoader 动态分配模型
        self.dm = DependencyManager(str(self.project_dir))
        self.model_selector = ModelSelector(user_models=user_models)
        self.soul_loader = AgentSoulLoader()

        # === 新增组件初始化 ===
        # 1. 状态管理器
        self.state_manager = StateManager(self.project_dir)
        self.state: Optional[WorkflowState] = None

        # 2. 工作流配置加载器（v3.4.1: 传入 model_selector 动态分配模型）
        self.config_loader = WorkflowConfigLoader(self.project_dir, self.model_selector)
        self.workflow_config = self.config_loader.load()

        # 3. 审批规则引擎
        self.approval_engine = ApprovalRulesEngine(self.project_dir)

        # 4. 飞书通知器
        self.notifier = FeishuNotifier(self.state_manager.state_dir)

        # === v3.7: 工程纪律组件（可选，feature flag 控制） ===
        self.skill_injector = None
        self.scorecard_engine = None
        self.task_profiler = None
        self.model_router = None
        if self.constraints.get("discipline_enabled", False):
            from skill_injector import SkillInjector
            from scorecard_engine import ScorecardEngine
            self.skill_injector = SkillInjector()
            self.scorecard_engine = ScorecardEngine()
            from task_profiler import TaskProfiler
            self.task_profiler = TaskProfiler(str(self.project_dir))
            from model_auto_router import ModelAutoRouter
            self.model_router = ModelAutoRouter()
            print(f"🔧 工程纪律模式已启用（SkillInjector + ScorecardEngine + TaskProfiler + AutoRouter）")

        # === 运行时状态 ===
        self.current_phase = "idle"
        self.completed_phases: List[str] = []
        self.iterations = 0
        self.start_time = None
        self.last_progress_time = None
        self.result = {
            'code': None,
            'test_result': None,
            'reflection': None,
            'fixed_code': None,
            'final_check': None,
            'iterations': 0,
            'passed': False,
            'task_progress': {},
            'agent_usage': {},
        }
        self.execution_order = []
        self.completed_tasks = set()
        self.context = {
            'original_requirements': requirements,
            'design_decisions': [],
            'coding_assumptions': [],
            'test_findings': [],
            'reflection_insights': [],
            'test_failures': [],
        }

        # 审批队列（人工确认项）
        self.pending_approvals: List[Dict] = []
        self.approval_message: Optional[str] = None  # 需要外发的审批/完成通知消息

        # === v3.4.1: 契约一致性自检（防错机制）
        self._validate_phase_contract()

    def _validate_phase_contract(self):
        """
        契约一致性自检（v3.4.1 防错机制）
        
        验证 workflow_config 中定义的阶段，必须都有对应的 _phase_xxx 实现方法
        避免出现"配置有这个阶段，但代码跳过不执行的静默失败
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 收集配置中的阶段
        config_phases = {p.id for p in self.workflow_config.phases}
        # 收集已实现的阶段方法
        impl_phases = {m.replace('_phase_', '') for m in dir(self) if m.startswith('_phase_')}
        
        missing = config_phases - impl_phases
        unused = impl_phases - config_phases
        
        if missing:
            error_msg = f"❌ 阶段契约失败：配置中有但实现缺失 = {missing}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        if unused:
            logger.warning(f"⚠️  阶段契约警告：实现了但配置不用 = {unused}")
        
        logger.info(f"✅ 阶段契约验证通过：{len(config_phases)} 个阶段全部就绪")

    async def run(self):
        """运行增强版工作流（支持配置化阶段 + 状态持久化 + 审批）"""
        self.start_time = datetime.now()
        self.last_progress_time = self.start_time

        # === 恢复或初始化状态 ===
        if self.resume_enabled and self.state_manager.can_resume():
            self.state = self.state_manager.load_state()
            resume_phase = self.state_manager.get_resume_phase()
            print(f"\n{'='*60}")
            print(f"🔄 恢复任务：{self.state.task_id}")
            print(f"   已完成的阶段：{self.state.completed_phases}")
            print(f"   从阶段恢复：{resume_phase}")
            print(f"{'='*60}\n")
            self._restore_from_state()
        else:
            self.state = self.state_manager.init_state(
                requirements=self.requirements,
                task_id=self.task_id
            )
            print(f"\n{'='*60}")
            print(f"🚀 Auto-Coding Enhanced (v3.7.4) 启动")
            print(f"{'='*60}")
            print(f"📋 需求：{self.requirements[:100]}...")
            print(f"📁 项目目录：{self.project_dir}")
            print(f"📄 工作流：{self.workflow_config.name}")
            print(f"⏱️  超时限制：{self.timeout_minutes} 分钟")
            print(f"{'='*60}\n")

        # === 确定执行的阶段列表 ===
        # 如果没有恢复状态，先做复杂度分析决定走哪些阶段
        if self.current_phase == "idle":
            complexity = await self._analyze_complexity()
            phases_to_run = self.config_loader.get_phases_for_complexity(complexity)
            print(f"📊 复杂度等级：{complexity}")
            print(f"📋 执行阶段：{[p.id for p in phases_to_run]}\n")
        else:
            # 恢复模式：从 workflow.yaml 获取完整阶段，过滤掉已完成的
            all_phases = self.workflow_config.phases
            phases_to_run = [p for p in all_phases if p.id not in self.completed_phases]
            print(f"📋 剩余阶段：{[p.id for p in phases_to_run]}\n")

        # === 创建 cron 监控（新任务才创建）===
        if self.current_phase == "idle" and self.resume_enabled:
            self._create_cron_monitor()

        # === 执行阶段（v3.3: while 循环支持 Reviewer 否决回退） ===
        phase_index = 0
        while phase_index < len(phases_to_run):
            phase_config = phases_to_run[phase_index]
            phase_index += 1
            # 检查超时
            if self._check_timeout():
                print(f"\n⏱️  任务超时（{self.timeout_minutes} 分钟），停止执行")
                self._save_final_state("timeout")
                return self.result

            # 检查是否有已 resolved 的审批（用户已回复，可继续）
            resolved_approval = self._check_resolved_approval()
            if resolved_approval:
                decision = resolved_approval["decision"]
                approval_id = resolved_approval["approval_id"]
                if decision == "approved":
                    print(f"\n▶️  审批已通过 [{approval_id}]，继续执行")
                    self.state_manager.resolve_approval(self.state, approval_id, "approved")
                elif decision == "rejected":
                    print(f"\n🛑 审批已终止 [{approval_id}]，停止任务")
                    self.state_manager.resolve_approval(self.state, approval_id, "rejected")
                    self._save_final_state("rejected")
                    return self.result
                elif decision == "skipped":
                    print(f"\n⏭️  审批已跳过 [{approval_id}]，继续执行")
                    self.state_manager.resolve_approval(self.state, approval_id, "skipped")
                # 清除 pending 标记
                self.notifier.clear_pending_approval()
                continue  # 继续当前阶段

            # 检查是否有未处理的审批（等待中）
            pending = self.state_manager.get_pending_approvals(self.state)
            if pending:
                print(f"\n⏸️  检测到未处理审批：")
                for a in pending:
                    print(f"   [{a['id']}] {a['operation']} - 等待人工确认")
                print(f"   请回复'确认 {a['id']}'继续 / '终止 {a['id']}'停止")
                self._save_final_state("approval_required")
                return self.result

            # 执行阶段
            phase_id = phase_config.id
            self.current_phase = phase_id
            
            # ===== Heartbeat 双轨机制：更新运行中标记 =====
            # Heartbeat 每 5 分钟扫到这个标记就会通报进度
            self.state_manager.mark_running(
                self.state,
                phase_id,
                phase_config.description
            )

            print(f"\n{'='*60}")
            print(f"📝 阶段：{phase_id} ({phase_config.description})")
            print(f"🤖 Agent：{phase_config.agent} | 🎯 模型：{phase_config.model}")
            print(f"{'='*60}")

            # 阶段前保存（标记进入阶段）
            self.state_manager.save_progress(self.state, current_phase=phase_id)

            try:
                # 执行阶段逻辑
                await self._run_phase(phase_config)

                # 阶段后审批检查（如 coding 阶段修改了敏感文件）
                approval_check = await self._check_phase_approval(phase_config)
                if approval_check and approval_check.requires_human:
                    approval_id = self.state_manager.push_approval(
                        self.state,
                        operation=f"phase:{phase_id}",
                        details={
                            "reason": approval_check.reason,
                            "files": approval_check.files,
                            "phase": phase_id,
                        }
                    )
                    # ===== Heartbeat 双轨机制：写审批标记 =====
                    self.state_manager.mark_approval_required(
                        self.state, 
                        approval_id, 
                        f"阶段审批：{phase_id}"
                    )
                    
                    # 生成飞书审批消息（由外层发送）
                    self.approval_message = self.notifier.send_approval_request(
                        task_id=self.state.task_id,
                        operation=f"{phase_id}: {approval_check.operation}",
                        files=approval_check.files,
                        project_dir=self.project_dir,
                        reason=approval_check.reason,
                    )
                    print(f"\n⏸️  审批请求已创建：[{approval_id}]")
                    print(f"   原因：{approval_check.reason}")
                    print(f"   已生成飞书通知，等待外层发送")
                    self._save_final_state(f"approval_required:{approval_id}")
                    return self.result

                # v3.7: Scorecard 检测 + Per-Skill Verification
                if self.scorecard_engine:
                    try:
                        signals = self._collect_signals(phase_id)
                        report = self.scorecard_engine.detect(phase_id, signals)
                        self._log_scorecard(report)
                        if self.scorecard_engine.is_blocking(report):
                            print(f"\n🔴 Scorecard 阻塞: {phase_id}")
                            print(f"   {report.summary.get('blocked', 0)} 阻塞项, {report.summary.get('warned', 0)} 警告")
                            self._save_final_state(f"blocked:scorecard:{phase_id}")
                            return {"status": "blocked", "phase": phase_id, "report": report}
                    except Exception as e:
                        print(f"   ⚠️  Scorecard 检测失败（降级跳过）: {e}")

                # v3.7: Task Profiler — 记录本次子 agent 执行数据（持续校准超时窗口）
                if self.task_profiler and self.result:
                    try:
                        from task_profiler import classify_task
                        task_data = self.result.get("task_progress", {}).get(phase_id, {})
                        elapsed = task_data.get("elapsed_seconds", 0) / 60
                        token_count = task_data.get("token_count", 0)
                        file_count = task_data.get("file_count", 0)
                        estimated = task_data.get("estimated_minutes", 0)
                        category = task_data.get("category") or classify_task(
                            task_data.get("prompt", ""), file_count
                        )
                        status = "timeout" if task_data.get("timed_out") else "completed"
                        self.task_profiler.record(
                            task_id=f"{self.state.task_id}:{phase_id}",
                            category=category,
                            model=phase_config.model,
                            phase=phase_id,
                            estimated_minutes=estimated,
                            actual_minutes=elapsed,
                            token_count=token_count,
                            file_count=file_count,
                            status=status,
                        )
                    except Exception as e:
                        pass  # profiler 失败不影响主流程

                # 标记阶段完成
                self.completed_phases.append(phase_id)
                self.state_manager.save_phase(self.state, phase_id, {
                    "agent": phase_config.agent,
                    "model": phase_config.model,
                    "completed_at": datetime.now().isoformat(),
                })
                # [Bugfix] 阶段成功后清零该阶段的失败记录，保证 recovery 预算按阶段独立
                self.state_manager.clear_phase_failures(self.state, phase_id)
                self._update_progress()
                print(f"\n✅ 阶段 {phase_id} 完成")

                # v3.6.2: Verifier 硬否决逻辑（带重试上限 + 退出机制）
                if phase_id == "review" and self.result.get("review_veto"):
                    # 递增重试次数
                    self.state.veto_retry_count += 1
                    veto_entry = {
                        "count": self.state.veto_retry_count,
                        "max": self.state.veto_retry_max,
                        "issues": len(self.result.get("review_issues", [])),
                        "veto_at": datetime.now().isoformat(),
                    }
                    self.state.veto_retry_history.append(veto_entry)
                    # 立即持久化否决计数
                    self.state_manager._save(self.state)
                    
                    if self.state.veto_retry_count >= self.state.veto_retry_max:
                        # 超过重试上限 → 升级给人类
                        print(f"\n⚠️  Reviewer 否决已达上限（{self.state.veto_retry_max}/{self.state.veto_retry_max}）")
                        print(f"   升级给人类决策：是否继续重写？")
                        approval_id = self.state_manager.push_approval(
                            self.state,
                            operation=f"veto_escalation:{phase_id}",
                            details={
                                "reason": f"Reviewer 连续否决 {self.state.veto_retry_count} 次，超出上限",
                                "veto_history": self.state.veto_retry_history,
                                "last_veto_feedback": self.context.get("veto_feedback", "")[:300],
                            }
                        )
                        self.state_manager.mark_approval_required(
                            self.state, approval_id,
                            f"Reviewer 否决升级：{self.state.veto_retry_count} 次"
                        )
                        self._save_final_state(f"approval_required:{approval_id}")
                        return self.result
                    
                    print(f"\n🔄 Reviewer 否决（{self.state.veto_retry_count}/{self.state.veto_retry_max}），回到 coding 重写")
                    if "coding" in self.completed_phases:
                        self.completed_phases.remove("coding")
                    # 将 veto 反馈加入 context 供 coding 阶段使用
                    veto_feedback = self.context.get("veto_feedback", "")
                    if veto_feedback:
                        print(f"   📋 已记录否决反馈（{len(veto_feedback)} 字）")
                    # 重新插入 coding 阶段
                    coding_phase = next((p for p in all_phases if p.id == "coding"), None)
                    review_idx = phases_to_run.index(phase_config) if phase_config in phases_to_run else len(phases_to_run)
                    if coding_phase and coding_phase not in phases_to_run[phase_index+1:]:
                        phases_to_run.insert(phase_index + 1, coding_phase)
                    continue  # 下一轮 while 循环会执行 re-inserted 的 coding

            except Exception as e:
                print(f"\n❌ 阶段 {phase_id} 失败：{e}")
                self.state_manager.save_progress(self.state, current_phase=f"failed:{phase_id}")
                
                # v3.6.2: 子 Agent 断线恢复
                error_str = str(e)
                self.state_manager.record_agent_failure(
                    self.state,
                    agent_id=phase_config.agent,
                    phase=phase_id,
                    error=error_str
                )
                
                if self.state_manager.has_recovery_budget(self.state):
                    recovery_action = self.state_manager.get_recovery_action(self.state, phase_id)
                    
                    if recovery_action == 'retry':
                        print(f"   🔄 Recovery: 重试阶段 {phase_id}（同模型重跑）")
                        # [Bugfix] phase_index +1 在 try 之前已执行，回退一个位置重插
                        phases_to_run.insert(phase_index - 1, phase_config)
                        phase_index -= 1
                        continue
                    elif recovery_action == 'fallback':
                        print(f"   🔄 Recovery: 降级重试阶段 {phase_id}（换 fallback 模型）")
                        # 切换到 fallback 模型
                        # 优先用 PhaseConfig 定义的 fallback_model，否则用原模型重试
                        fallback = getattr(phase_config, 'fallback_model', None) or phase_config.model
                        if fallback and fallback != phase_config.model:
                            print(f"      模型: {phase_config.model} → {fallback}")
                            fallback_config = PhaseConfig(
                                id=phase_id,
                                name=phase_config.name,
                                description=phase_config.description,
                                agent=phase_config.agent,
                                model=fallback,
                                gates=phase_config.gates,
                            )
                            phases_to_run.insert(phase_index - 1, fallback_config)
                        else:
                            phases_to_run.insert(phase_index - 1, phase_config)
                        phase_index -= 1
                        continue
                    elif recovery_action == 'escalate':
                        print(f"   ⏸️  Recovery: 升级给人类决策")
                        approval_id = self.state_manager.push_approval(
                            self.state,
                            operation=f"agent_failure:{phase_id}",
                            details={
                                "reason": f"子 Agent 失败 {self.state.agent_recovery_attempts} 次，需人工决策",
                                "error": error_str[:300],
                                "phase": phase_id,
                                "agent": phase_config.agent,
                            }
                        )
                        self.state_manager.mark_approval_required(
                            self.state, approval_id,
                            f"子 Agent 失败升级：{phase_id}"
                        )
                        self._save_final_state(f"approval_required:{approval_id}")
                        return self.result
                else:
                    print(f"   ❌ Recovery 预算耗尽（尝试 {self.state.agent_recovery_attempts} 次），任务失败")
                    self._save_final_state("failed")
                    raise

        # === 工作流完成 ===
        # v3.4: 可选架构健康检查（improve-architecture）
        await self._check_architecture_health()
        
        self._save_final_state("completed")
        self._print_final_report()
        return self.result

    async def _check_architecture_health(self):
        """
        架构健康检查（v3.4: 嵌入 improve-architecture 技能）
        
        可选触发，发现深层耦合问题
        """
        code = self.result.get('code', '')
        if not code or len(code) < 200:
            return  # 代码太短，跳过
        
        print(f"\n{'='*60}")
        print(f"🏗️  架构健康检查（improve-architecture）")
        print(f"{'='*60}")
        
        arch_prompt = (
            f"你是架构师。对以下代码做架构健康检查。\n\n"
            f"## 代码\n```python\n{code[:3000]}\n```\n\n"
            f"## 检查维度\n"
            f"1. 模块是否过浅（接口和实现一样复杂）？\n"
            f"2. 纯函数只为测试提取，但真实 bug 在调用处 → 缺少 locality？\n"
            f"3. 紧耦合泄漏到 seam 之外 → 边界模糊？\n"
            f"4. 删除这个模块，复杂度是否消失（它是透传）？\n\n"
            f"## 输出格式\n"
            f"### 架构改进机会（编号列表）\n"
            f"1. 文件: xxx | 问题: xxx | 方案: xxx | 收益: xxx\n\n"
            f"如果没有明显问题，输出：架构健康，无改进机会。"
        )
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=None)
            print(f"   🏗️  架构检查中...")
            result = await worker.execute(WorkerTask(
                id="arch-check", description="架构健康检查", prompt=arch_prompt
            ))
            if result.success:
                self.context["architecture_health"] = result.output
                print(f"   ✅ 架构检查完成")
                # 打印发现
                if "无改进机会" not in result.output:
                    print(f"   📋 发现架构改进机会：")
                    for line in result.output.split("\n"):
                        if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                            print(f"      {line.strip()}")
            else:
                print(f"   ⚠️  架构检查失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  架构检查调用异常: {e}")
        
        print(f"{'='*60}\n")

    async def _run_phase(self, phase_config: PhaseConfig):
        """执行单个阶段"""
        phase_id = phase_config.id

        # v3.7: 技能注入（阶段启动时注入技能内容到 self.context）
        if self.skill_injector:
            try:
                skill_prompt, meta = self.skill_injector.inject_for_phase(phase_id)
                if skill_prompt:
                    self.context["_injected_skill_prompt"] = skill_prompt
                    print(f"   📥 技能注入: {meta.get('skills', [])} (~{meta.get('token_estimate', 0)} tokens)")
            except Exception as e:
                print(f"   ⚠️  技能注入失败（降级跳过）: {e}")

        # v3.7: 自动模型路由（Pro 推理 / Flash 执行）
        if self.model_router:
            try:
                from task_profiler import classify_task
                model, thinking = self.model_router.route(
                    phase=phase_id,
                    category=self.context.get("_task_category"),
                    context_tokens=self.context.get("_context_tokens", 0),
                )
                print(f"   🧠 Auto路由: {model} (thinking={thinking})")
                # 写入 context 供子 agent spawn 时使用
                self.context["_routed_model"] = model
                self.context["_routed_thinking"] = thinking
            except Exception as e:
                print(f"   ⚠️  路由决策失败（降级跳过）: {e}")

        if phase_id == "design":
            await self._phase_design(phase_config)
        elif phase_id == "decomposition":
            await self._phase_decomposition(phase_config)
        elif phase_id == "coding":
            await self._phase_coding(phase_config)
        elif phase_id == "testing":
            await self._phase_testing(phase_config)
        elif phase_id == "reflection":
            await self._phase_reflection(phase_config)
        elif phase_id == "optimization":
            await self._phase_optimization(phase_config)
        elif phase_id == "verification":
            await self._phase_verification(phase_config)
        else:
            print(f"   ⚠️  未知阶段 {phase_id}，跳过")

    async def _phase_testing(self, phase: PhaseConfig):
        """阶段：功能测试（v3.4: 嵌入 TDD 红-绿-重构循环）"""
        print(f"   运行功能测试（TDD 模式）...")
        
        code = self.result.get('code', '')
        
        # v3.4: TDD 垂直切片 — 一次一个测试，红→绿→重构
        tdd_prompt = self._wrap_prompt(
            f"你是测试工程师。使用 TDD 红-绿-重构循环编写测试。\n\n"
            f"## 待测试代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
            f"## TDD 规则\n"
            f"1. 垂直切片：一次一个测试，写最小实现通过\n"
            f"2. 测试行为不测实现：只验证 public API\n"
            f"3. 红→绿→重构：先写失败测试，再写代码通过，再重构\n"
            f"4. 每个测试要能存活于内部重构之后\n\n"
            f"## 输出格式\n"
            f"### 测试用例\n"
            f"```python\n# test_xxx.py\ndef test_xxx():\n    ...\n```\n\n"
            f"### 测试结果\n每个测试的 pass/fail 状态\n\n"
            f"### 总结\n通过/失败数 + 建议"
        )
        
        try:
            from workers.testing_worker import TestingWorker
            from workers.base_worker import WorkerTask
            worker = TestingWorker(model_selector=self.model_selector, model_override=phase.model)
            print(f"   🧪 TDD 测试生成...")
            result = await worker.execute(WorkerTask(
                id="test", description="TDD 测试", prompt=tdd_prompt
            ))
            if result.success:
                self.context['test_output'] = result.output
                # 从输出判断测试是否通过
                output_lower = result.output.lower()
                passed = ('pass' in output_lower and 'fail' not in output_lower) or '通过' in result.output
                self.result['test_passed'] = passed
                print(f"   ✅ TDD 测试完成")
            else:
                self.result['test_passed'] = False
                print(f"   ❌ 测试失败: {result.error}")
        except Exception as e:
            self.result['test_passed'] = False
            print(f"   ⚠️  测试调用异常: {e}")
        
        self.state_manager.save_progress(self.state, results=self.result, context=self.context)

    async def _phase_optimization(self, phase: PhaseConfig):
        """阶段：代码优化（v3.4: 调用 glm-5.1 优化器）"""
        print(f"   优化代码...")
        
        code = self.result.get('code', '')
        review = self.context.get('veto_feedback', '') or self.result.get('reflection', '')
        
        opt_prompt = self._wrap_prompt(
            f"你是代码优化工程师。根据审查结果进行深度优化：优雅优先、性能敏感、消除冗余。\n\n"
            f"## 审查反馈\n{review[:2000] if review else '无审查反馈'}\n\n"
            f"## 当前代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
            f"## 需求\n{self.requirements}\n\n"
            f"输出优化后的完整代码 + 逐条说明优化点及收益。"
        )
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=phase.model)
            print(f"   🔧 调用 {phase.model} 优化...")
            result = await worker.execute(WorkerTask(
                id="optimize", description="代码优化", prompt=opt_prompt
            ))
            if result.success:
                import re
                code_blocks = re.findall(r'```(?:python|javascript|typescript)?\n(.*?)```', result.output, re.DOTALL)
                self.result["code"] = "\n\n".join(code_blocks) if code_blocks else result.output
                self.context["optimization_notes"] = result.output
                print(f"   ✅ 优化完成")
            else:
                print(f"   ⚠️  优化失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  优化调用异常: {e}")
        
        self.state_manager.save_progress(self.state, results=self.result, context=self.context)

    async def _run_debug_subroutine(self, failure_context: str = ""):
        """
        调试子流程（v3.4: 嵌入 diagnose 技能）
        
        6 阶段：建循环→复现→假设→插桩→修复→清理
        当测试失败或 Reviewer 否决时触发
        """
        print(f"\n{'='*60}")
        print(f"🔍 调试子流程启动")
        print(f"{'='*60}")
        
        code = self.result.get('code', '')
        debug_prompt = (
            f"你是调试专家。按 6 阶段系统化调试流程排查问题。\n\n"
            f"## 失败上下文\n{failure_context}\n\n"
            f"## 代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
            f"## 6 阶段\n"
            f"Phase 1: 建反馈循环 — 可复现的 pass/fail 信号\n"
            f"Phase 2: 复现 — 确认 bug 和描述一致\n"
            f"Phase 3: 假设 — 3-5 个可证伪假设，排优先级\n"
            f"Phase 4: 插桩 — 带 [DEBUG-xxx] 标签的定向日志\n"
            f"Phase 5: 修复 — 先写回归测试再修复\n"
            f"Phase 6: 清理 + 复盘\n\n"
            f"输出：每个阶段的发现 + 最终修复方案。"
        )
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=None)
            print(f"   🔍 调试分析中...")
            result = await worker.execute(WorkerTask(
                id="debug", description="系统化调试", prompt=debug_prompt
            ))
            if result.success:
                self.context["debug_result"] = result.output
                print(f"   ✅ 调试完成，已记录分析结果")
            else:
                print(f"   ⚠️  调试失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  调试调用异常: {e}")
        
        print(f"{'='*60}\n")

    async def _grill_with_docs(self, requirements: str) -> str:
        """
        Grill-With-Docs 需求对齐（v3.4: 嵌入 analyze 阶段）
        
        结构化追问，一次一个，走完决策树：
        目标→范围→行为→接口→数据→约束→验收
        """
        grill_prompt = (
            f"你是一位需求分析专家。使用 grill-with-docs 方法对以下需求做结构化追问。\n\n"
            f"## 需求\n{requirements}\n\n"
            f"## 追问决策树（一次一个核心问题）\n"
            f"1. 目标：解决什么问题？用户是谁？\n"
            f"2. 范围：做什么？不做什么？\n"
            f"3. 行为：正常流程？异常流程？\n"
            f"4. 接口：输入/输出？模块交互？\n"
            f"5. 数据：存储？格式？迁移？\n"
            f"6. 约束：性能？安全？兼容？\n"
            f"7. 验收：怎么证明做完了？\n\n"
            f"每个问题给推荐答案和理由。识别领域术语写入 CONTEXT.md。"
        )
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=None)
            print(f"   🔥 Grill-with-docs 需求对齐...")
            result = await worker.execute(WorkerTask(
                id="grill", description="需求对齐", prompt=grill_prompt
            ))
            if result.success:
                print(f"   ✅ 需求对齐完成")
                return result.output
            else:
                print(f"   ⚠️  需求对齐失败: {result.error}")
                return ""
        except Exception as e:
            print(f"   ⚠️  需求对齐调用异常: {e}")
            return ""

    async def _analyze_complexity(self) -> str:
        """分析需求复杂度（v3.3: 使用 ComplexityAnalyzer）"""
        result = analyze_complexity(self.requirements)
        print(f"   📊 复杂度分数: {result.score}/100")
        for reason in result.reasons:
            print(f"   • {reason}")
        self.result["complexity_details"] = {
            "level": result.level,
            "score": result.score,
            "reasons": result.reasons,
            "estimated_duration": result.estimated_duration,
        }
        return result.level

    async def _phase_design(self, phase: PhaseConfig):
        """阶段：技术方案设计（v3.4: 嵌入 grill-with-docs 需求对齐）"""
        print(f"   设计技术方案...")
        
        # v3.4: Grill-With-Docs 需求对齐
        grill_output = await self._grill_with_docs(self.requirements)
        if grill_output:
            self.context["grill"] = grill_output
            print(f"   ✅ 需求对齐完成（grill-with-docs）")
        
        # 调用 EngineeringWorker 做实际设计
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=phase.model)
            design_prompt = self._wrap_prompt(f"""分析需求并设计技术方案。

## 需求
{self.requirements}

## 上下文
{self.context.get('grill', '')[:500]}

## 输出格式
### 技术选型
- 语言/框架：xxx
- 核心库：xxx

### 目录结构
```
src/
  main.py
  ...
```

### 关键设计决策
1. xxx（理由）
2. xxx（理由）""")
            print(f"   🚀 调用 {phase.model} 生成设计方案...")
            result = await worker.execute(WorkerTask(
                id="design", description="技术方案设计", prompt=design_prompt
            ))
            if result.success:
                self.context["design"] = result.output
                print(f"   ✅ 设计方案完成")
            else:
                print(f"   ❌ 设计失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  设计调用异常: {e}")
        
        self.state_manager.save_progress(self.state, context=self.context)
        print(f"   ✅ 设计阶段完成")

    async def _phase_decomposition(self, phase: PhaseConfig):
        """阶段：任务分解和依赖管理"""
        print(f"   拆解需求为可执行任务...")
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=phase.model)
            decomp_prompt = self._wrap_prompt(f"""根据技术方案拆解任务，定义依赖关系。

## 需求
{self.requirements}

## 设计方案
{self.context.get('design', '')[:1000]}

## 输出格式
### 任务列表
| ID | 名称 | 描述 | 依赖 |
|----|------|------|------|
| t1 | 核心实现 | xxx | - |

### 依赖关系
- t1 → t2 → t3""")
            print(f"   🚀 调用 {phase.model} 做任务拆解...")
            result = await worker.execute(WorkerTask(
                id="decomp", description="任务拆解", prompt=decomp_prompt
            ))
            if result.success:
                self.context["decomposition"] = result.output
                self.context["tasks"] = [{"id": "t1", "name": "核心实现", "description": self.requirements}]
                print(f"   ✅ 任务拆解完成")
            else:
                print(f"   ❌ 拆解失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  拆解调用异常: {e}")
            # Fallback: 简化版任务拆解
            self.context["tasks"] = [{"id": "task-1", "name": "核心实现", "description": self.requirements}]
        
        self.state_manager.save_progress(self.state, context=self.context)
        print(f"   ✅ 拆解为 {len(self.context['tasks'])} 个任务")

    async def _phase_coding(self, phase: PhaseConfig):
        """阶段：代码实现（v3.4: 使用 phase_config.model + EngineeringWorker）"""
        print(f"   实现代码...")

        # 从需求中推断将要修改的文件
        files_to_edit = self._detect_files_to_edit()
        if files_to_edit:
            decision = self.approval_engine.check_edit(files_to_edit)
            if decision.requires_human:
                print(f"   ⚠️  文件修改需要审批：{decision.reason}")
                self.pending_approvals.append({
                    "phase": "coding",
                    "decision": decision,
                })
                return

        # v3.4: 调用 EngineeringWorker 实际编码
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=phase.model)
            
            # 构建编码 prompt
            coding_prompt = (
                f"按 Karpathy 铁律生成代码。\n\n"
                f"## 前置要求（必须先做第 1 再写代码）\n"
                f"1. 【变更影响分析】编码前先输出：\n"
                f"   ---变更影响分析---\n"
                f"   修改内容：[一句话描述要改什么]\n"
                f"   可能影响的关联点：[1.xxx 2.xxx 3.xxx]（阶段ID/配置/字符串/方法名等）\n"
                f"   需要同步修改的地方：[列出所有需要同步改的地方]\n"
                f"   ------------------\n"
                f"2. 【编码】手术刀修改、不添加未请求功能。\n\n"
                f"## 需求\n{self.requirements}\n\n"
                f"## 上下文\n"
            )
            if self.context.get("design"):
                coding_prompt += f"设计决策：{self.context['design'][:500]}\n"
            if self.context.get("grill"):
                coding_prompt += f"需求对齐：{self.context['grill'][:500]}\n"
            coding_prompt += "\n请先输出变更影响分析，再输出代码。"
            coding_prompt = self._wrap_prompt(coding_prompt)
            
            print(f"   🚀 调用 {phase.model} 生成代码...")
            result = await worker.execute(WorkerTask(
                id="coding", description="代码实现", prompt=coding_prompt
            ))
            
            if result.success:
                # 提取代码块
                import re
                code_blocks = re.findall(r'```(?:python|javascript|typescript|java|go|rust)?\n(.*?)```', result.output, re.DOTALL)
                if code_blocks:
                    self.result["code"] = "\n\n".join(code_blocks)
                else:
                    self.result["code"] = result.output
                print(f"   ✅ 代码生成完成 ({len(self.result['code'])} 字符)")
            else:
                self.result["code"] = f"# 编码失败: {result.error}"
                print(f"   ❌ 编码失败: {result.error}")
        except Exception as e:
            self.result["code"] = f"# 调用异常: {str(e)}"
            print(f"   ⚠️  编码调用异常: {e}")
        
        self.state_manager.save_progress(self.state, results=self.result)

    async def _phase_reflection(self, phase: PhaseConfig) -> dict:
        """阶段：代码审查和反思（v3.4: 调用模型 + ReviewerWorker 否决权 + zoom-out）"""
        print(f"   审查代码质量...")
        
        code = self.result.get('code', '')
        req = self.requirements
        
        # === v3.4.1: 审查顺序（必须前 2 条通过才能看代码质量） ===
        review_prompt = self._wrap_prompt(
            f"你是一位代码审查专家。严格按顺序审查，必须先过第 1、2 条才能看第 3 条。\n\n"
            f"## 审查顺序（违反顺序直接否决）\n"
            f"1. 🔧 契约一致性：阶段ID、配置、接口、字符串是否对齐？有没有漏改关联点？\n"
            f"   - 检查方法：列出所有与变更相关的字符串、配置、方法名\n"
            f"   - 检查是否有遗漏的同步修改\n"
            f"   - 发现不一致 = 🔴 阻塞项，必须否决\n"
            f"2. 🧩 影响范围：修改有没有漏了关联点？（日志/异常/审批条件/回退逻辑等）\n"
            f"   - 思考：这个改动会影响哪些其他地方？\n"
            f"   - 检查：有没有遗漏的关联修改\n"
            f"   - 发现漏改 = 🔴 阻塞项，必须否决\n"
            f"3. 📝 代码质量：逻辑、风格、安全、可读性\n\n"
            f"## zoom-out 全局理解\n"
            f"1. 这段代码在系统中的位置和职责\n"
            f"2. 和哪些模块/外部系统交互\n"
            f"3. 调用者是谁、依赖了什么\n\n"
            f"## 代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
            f"## 输出格式\n"
            f"### 整体评价\n一句话总结（必须提到契约和影响范围检查结果）\n"
            f"### 问题列表\n🔴 [类别] 第X行：问题描述 — 修复建议\n🟡 [类别] 第X行：问题描述 — 修复建议\n"
            f"### 值得肯定\n- 优点\n\n"
            f"注意：需求明确要求的做法优先于极简主义，不要在需求约束上挑刺。"
        )
        
        try:
            from workers.engineering_worker import EngineeringWorker
            from workers.base_worker import WorkerTask
            worker = EngineeringWorker(model_selector=self.model_selector, model_override=phase.model)
            print(f"   🔍 契约 + 影响 + 代码审查 (model: {phase.model})...")
            result = await worker.execute(WorkerTask(
                id="review", description="代码审查", prompt=review_prompt
            ))
            review_text = result.output if result.success else ""
        except Exception as e:
            review_text = ""
            print(f"   ⚠️  审查调用异常: {e}")
        
        self.result["reflection"] = review_text
        
        # ReviewerWorker 否决权
        reviewer = ReviewerWorker()
        review_result = reviewer.parse_review_output(review_text)
        
        self.result["review_passed"] = review_result.passed
        self.result["review_veto"] = review_result.veto
        self.result["review_issues"] = [
            {"severity": i.severity, "category": i.category, "description": i.description}
            for i in review_result.issues
        ]
        
        if review_result.veto:
            print(f"   🚫 Reviewer 否决！发现 {sum(1 for i in review_result.issues if i.severity == '🔴')} 个阻塞项")
            veto_prompt = reviewer.build_veto_prompt(review_result, code)
            self.context["veto_feedback"] = veto_prompt
            self.state_manager.save_progress(self.state, results=self.result, context=self.context)
            print(f"   🔄 触发重写循环")
        else:
            print(f"   ✅ 审查通过")
        
        self.state_manager.save_progress(self.state, results=self.result)
        return {"review_result": review_result, "review_text": review_text}

    async def _phase_verification(self, phase: PhaseConfig):
        """阶段：交付验证（v3.4: 调用 TestingWorker 实际验证）"""
        print(f"   运行测试...")
        # 检查测试命令是否需要审批
        test_cmd = "pytest"
        decision = self.approval_engine.check_run(test_cmd)
        if decision.requires_human:
            print(f"   ⚠️  测试命令需要审批：{decision.reason}")
            self.pending_approvals.append({
                "phase": "verification",
                "decision": decision,
            })
            return

        # 调用 TestingWorker 做实际验证
        try:
            from workers.testing_worker import TestingWorker
            from workers.base_worker import WorkerTask
            worker = TestingWorker(model_selector=self.model_selector, model_override=phase.model)
            code = self.result.get('code', '')
            verify_prompt = self._wrap_prompt(
                f"对以下代码进行最终交付验证：功能完整性、边界覆盖、集成正确性。\n\n"
                f"## 原始需求\n{self.requirements}\n\n"
                f"## 代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
                f"逐条验证 + 通过/不通过 + 具体证据。"
            )
            print(f"   🧪 调用 TestingWorker 验证...")
            result = await worker.execute(WorkerTask(
                id="verify", description="交付验证", prompt=verify_prompt
            ))
            if result.success:
                self.context["verification_output"] = result.output
                # 从验证输出判断是否通过
                output_lower = result.output.lower()
                passed = "通过" in result.output and "未通过" not in result.output
                self.result["test_passed"] = passed
                print(f"   {'✅' if passed else '❌'} 验证完成")
            else:
                self.result["test_passed"] = False
                print(f"   ❌ 验证失败: {result.error}")
        except Exception as e:
            self.result["test_passed"] = False
            print(f"   ⚠️  验证调用异常: {e}")
        
        self.state_manager.save_progress(self.state, results=self.result, test_passed=self.result.get('test_passed', False))

    async def _check_phase_approval(self, phase_config: PhaseConfig) -> Optional[ApprovalDecision]:
        """
        阶段完成后检查是否需要人工审批
        
        基于 phase_config.gates 和 approval_rules 双重检查
        """
        # 1. 检查 phase 配置中的 gates
        for gate in phase_config.gates:
            if gate.get("type") == "path-check":
                # 检测是否修改了敏感路径
                files = self._detect_modified_files()
                if files:
                    decision = self.approval_engine.check_edit(files)
                    if decision.requires_human:
                        return decision

        # 2. 检查是否有 pending 的审批
        if self.pending_approvals:
            pending = self.pending_approvals.pop(0)
            return pending["decision"]

        return None

    def _detect_files_to_edit(self) -> List[str]:
        """检测将要修改的文件（v3.4: 从上下文推断）"""
        # 从之前的阶段输出推断
        code = self.result.get("code", "")
        if not code:
            # 尚未生成代码，根据需求推断
            req_lower = self.requirements.lower()
            detected_files = []
            if any(kw in req_lower for kw in ["api", "接口", "endpoint", "路由", "route"]):
                detected_files.extend(["src/api.py", "src/routes.py"])
            if any(kw in req_lower for kw in ["数据", "model", "模型", "database", "db"]):
                detected_files.extend(["src/models.py", "src/db.py"])
            if any(kw in req_lower for kw in ["前端", "ui", "页面", "component", "react", "vue"]):
                detected_files.extend(["src/App.tsx", "src/components/"])
            if any(kw in req_lower for kw in ["测试", "test", "spec"]):
                detected_files.extend(["tests/test_main.py", "src/main_test.py"])
            if detected_files:
                return detected_files
            return ["src/main.py"]
        return []  # 已有代码时不预检，由 approval gate 在修改后检查

    def _wrap_prompt(self, base_prompt: str) -> str:
        """包装 prompt，按需追加注入的技能内容。
        
        仅当 discipline_enabled 且 _injected_skill_prompt 存在时才追加。
        """
        if self.constraints.get("discipline_enabled") and self.context.get("_injected_skill_prompt"):
            return f"{base_prompt}\n\n## 技能注入\n{self.context['_injected_skill_prompt']}"
        return base_prompt

    def _detect_modified_files(self) -> List[str]:
        """检测已修改的文件（v3.4: 基于状态追踪）"""
        modified = []
        # 从状态中追踪的文件
        if self.state and hasattr(self.state, 'modified_files'):
            modified = list(self.state.modified_files)
        # 简化版：根据当前阶段输出判断
        if self.result.get('code'):
            modified.append("src/main.py")
        if self.context.get('test_output'):
            modified.append("tests/test_main.py")
        return list(set(modified))  # 去重

    def _restore_from_state(self):
        """从持久化状态恢复运行时状态"""
        if not self.state:
            return
        self.current_phase = self.state.current_phase
        self.completed_phases = list(self.state.completed_phases)
        self.context = dict(self.state.context)
        self.result = dict(self.state.results)
        self.iterations = self.state.iterations

    def _save_final_state(self, status: str):
        """保存最终状态，并写心跳标记（Heartbeat 双轨机制）"""
        if self.state:
            self.state_manager.save_progress(
                self.state,
                current_phase=status,
                results=self.result,
                context=self.context,
                iterations=self.iterations,
            )
            
            # ===== Heartbeat 双轨机制：写标记文件 =====
            # 不再依赖 Cron 高频轮询，Worker 主动写标记，Heartbeat 巡检扫
            if status == "completed":
                summary = self.result.get("final_summary", "") or "任务完成"
                self.state_manager.mark_completed(self.state, summary)
            elif status in {"failed", "rejected", "timeout"}:
                error = self.result.get("error", f"任务{status}")
                self.state_manager.mark_failed(self.state, error)
            elif status.startswith("approval_required"):
                approval_id = status.split(":")[-1] if ":" in status else "unknown"
                self.state_manager.mark_approval_required(self.state, approval_id, "等待用户确认")
        
        # 终态时删除 cron 监控（兼容旧方案，逐步淘汰）
        final_states = {"completed", "failed", "rejected", "timeout"}
        if status in final_states:
            self._delete_cron_monitor()

    def _check_timeout(self) -> bool:
        """检查是否超时"""
        if not self.start_time:
            return False
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        return elapsed >= self.timeout_minutes

    def _update_progress(self):
        """更新进度时间"""
        self.last_progress_time = datetime.now()

    def _collect_signals(self, phase: str) -> dict:
        """从阶段执行结果中收集可观测信号。
        
        v3.7: 为 ScorecardEngine 提供阶段质量信号。
        """
        signals = {}

        # ── 通用信号 ──
        code = self.result.get("code", "")
        if code:
            signals["modified_file_count"] = 1  # 默认至少修改了主文件
        else:
            signals["modified_file_count"] = 0

        # 额外功能检测：比对 requirements 中的关键词密度
        req_keywords = len(self.requirements.split())
        code_lines = code.count("\n") if code else 0
        signals["extra_features_added"] = max(0, code_lines - req_keywords * 3) if code else 0

        # ── 阶段特定信号 ──
        if phase == "testing":
            signals["testing_phase_executed"] = bool(
                self.context.get("test_output") or self.result.get("test_passed") is not None
            )

        if phase == "reflection":
            reflection = self.result.get("reflection", "")
            signals["zoom_out_executed"] = "zoom-out" in str(reflection).lower() or "全局" in str(reflection)

        if phase == "verification":
            signals["test_passed"] = self.result.get("test_passed", False)

        if phase == "coding":
            # 代码行数作为修改规模信号
            signals["modified_file_count"] = max(1, (code.count("\n") // 100) if code else 0)
            # 额外功能：超过简单需求的代码量
            signals["extra_features_added"] = (
                max(0, code.count("\n") - 200) if code and code.count("\n") > 200 else 0
            )

        return signals

    def _log_scorecard(self, report):
        """将 ScorecardReport 写入阶段日志文件。
        
        v3.7: Scorecard 检测结果持久化到 .auto-coding/logs/。
        降级策略：写入失败时打印警告，不抛异常。
        """
        try:
            log_dir = Path(self.project_dir) / ".auto-coding" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            phase_order = len(self.completed_phases) + 1
            log_path = log_dir / f"{phase_order:02d}-{report.phase}-scorecard.log"
            log_path.write_text(self.scorecard_engine.format_report(report))
            print(f"   📊 Scorecard 日志: {log_path.name}")
        except Exception as e:
            print(f"   ⚠️  Scorecard 日志写入失败: {e}")

    def _print_final_report(self):
        """打印最终报告"""
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        print(f"\n{'='*60}")
        print(f"🎉 Auto-Coding Enhanced 完成！")
        print(f"{'='*60}")
        print(f"📊 总耗时：{elapsed:.1f} 分钟")
        print(f"📋 完成阶段：{self.completed_phases}")
        print(f"🔄 迭代次数：{self.iterations}")
        print(f"✅ 测试：{'通过' if self.result.get('test_passed') else '未通过'}")
        print(f"📁 项目目录：{self.project_dir}")
        print(f"💾 状态文件：{self.state_manager.state_file}")
        print(f"{'='*60}")

        # 如果配置了完成通知
        if self.approval_engine.should_notify_on_complete():
            self._send_completion_notification(elapsed)

    def _create_cron_monitor(self):
        """
        创建 cron job 监控任务进度
        
        每 5 分钟检查一次，直到任务完成
        """
        if not self.state:
            return
        
        cron_name = f"ac-monitor-{self.state.task_id}"
        project_dir = str(self.project_dir)
        task_id = self.state.task_id
        check_script = Path(__file__).parent / "check_auto_coding_status.py"
        
        # 构建 cron 消息
        cron_message = (
            f"检查 Auto-Coding 任务状态\\n"
            f"- 任务ID: {task_id}\\n"
            f"- 项目目录: {project_dir}\\n"
            f"- 执行命令: python3 {check_script} {project_dir} --task-id {task_id}\\n"
            f"- 脚本输出 JSON，包含 should_notify 和 should_delete_cron\\n"
            f"- 如果 should_notify=true → 调 message tool 发飞书通知（用脚本输出的 message 字段）\\n"
            f"- 如果 should_delete_cron=true → 执行 openclaw cron rm {cron_name}"
        )
        
        cmd = [
            "openclaw", "cron", "add",
            "--name", cron_name,
            "--every", "5m",
            "--message", cron_message,
            "--session", "main",
            "--timeout-seconds", "60",
            "--tools", "exec,message",
        ]
        
        try:
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"\n✅ Cron 监控已创建: {cron_name}")
            print(f"   每 5 分钟检查一次")
            print(f"   命令: openclaw cron show {cron_name}")
            return cron_name
        except subprocess.CalledProcessError as e:
            print(f"\n⚠️  Cron 创建失败: {e}")
            print(f"   stderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"\n⚠️  openclaw CLI 不可用，Cron 监控未创建")
            print(f"   任务完成后不会自动通知")
            return None

    def _delete_cron_monitor(self):
        """删除 cron job"""
        if not self.state:
            return
        cron_name = f"ac-monitor-{self.state.task_id}"
        try:
            import subprocess
            subprocess.run(
                ["openclaw", "cron", "rm", cron_name],
                capture_output=True, text=True, check=True
            )
            print(f"✅ Cron 监控已删除: {cron_name}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # 可能已经删了或不存在

    def _send_completion_notification(self, elapsed_minutes: float):
        """发送完成通知（生成飞书消息，由外层发送）"""
        msg = self.notifier.send_completion_report(
            task_id=self.state.task_id if self.state else "unknown",
            project_dir=self.project_dir,
            elapsed_minutes=elapsed_minutes,
            completed_phases=self.completed_phases,
            requirements=self.requirements,
            test_passed=self.result.get("test_passed", False),
        )
        print(f"\n📢 任务完成通知")
        print(msg)
        # 外层可获取 self.approval_message 并通过 message tool 发送
        self.approval_message = msg  # 复用字段存完成通知

    # ========================================================================
    # 审批恢复（供外层调用）
    # ========================================================================

    def _check_resolved_approval(self) -> Optional[Dict[str, str]]:
        """
        检查是否有用户已回复的审批

        从 pending_approval.json 中读取用户决定
        """
        pending_info = self.notifier.get_pending_approval_info()
        if not pending_info:
            return None
        if pending_info.get("status") in ["approved", "rejected", "skipped"]:
            return {
                "approval_id": pending_info["approval_id"],
                "decision": pending_info["status"],
            }
        return None

    def handle_user_message(self, user_text: str) -> Optional[Dict[str, Any]]:
        """
        处理用户消息，检查是否为审批回复

        供外层（OpenClaw session）调用

        Returns:
            None: 不是审批回复
            dict: {"action": "approved|rejected|skipped", "approval_id": str, "task_id": str}
        """
        reply = self.notifier.parse_approval_reply(user_text)
        if not reply:
            return None

        approval_id = reply["approval_id"]
        decision = reply["decision"]

        # 更新 pending_approval 状态
        self.notifier.resolve_pending_approval(approval_id, decision)

        # 获取任务 ID
        pending_info = self.notifier.get_pending_approval_info()
        task_id = pending_info.get("task_id") if pending_info else None

        return {
            "action": decision,
            "approval_id": approval_id,
            "task_id": task_id,
        }


# === CLI 入口 ===
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("用法：python workflow_enhanced.py <需求描述> [项目目录]")
            print("示例：python workflow_enhanced.py '实现用户登录功能' ./my-project")
            sys.exit(1)

        requirements = sys.argv[1]
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "./auto-coding-output"

        workflow = AutoCodingWorkflowEnhanced(
            requirements=requirements,
            project_dir=project_dir,
        )
        await workflow.run()

    asyncio.run(main())
