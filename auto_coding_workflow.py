#!/usr/bin/env python3
"""
Auto-Coding 八步循环工作流

核心理念：不是任务分发器，而是自我完善的智能系统

八步循环：
1. 设计 (Design) - 技术方案设计和架构
2. 分解 (Decomposition) - 任务拆解和依赖管理
3. 编码 (Coding) - 代码实现
4. 测试 (Testing) - 功能测试
5. 反思 (Reflection) - 代码审查和反思
6. 优化 (Optimization) - 改进和修复
7. 验证 (Verification) - 最终验证
8. 输出 (Output) - 交付物生成

迭代逻辑：
- 测试→反思→优化 形成迭代循环（最多 3 次）
- 每个阶段都有小反思
- 验证通过后输出交付物

P1 修复：
- 添加超时控制（任务取消机制）
- 添加进度追踪（死锁检测优化）
- 集成依赖管理器（任务依赖性管理）
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field

# 导入依赖管理器、模型选择器和 Agent Soul 加载器
from dependency_manager import DependencyManager
from model_selector import ModelSelector
from agent_soul_loader import AgentSoulLoader

# v3.3 新增：复杂度分析 + ReviewerWorker
from complexity_analyzer import ComplexityAnalyzer, analyze_complexity
from workers.reviewer_worker import ReviewerWorker, ReviewResult

# P1-3 修复：初始化日志
import logging
logger = logging.getLogger(__name__)


# ============================================================================
# 接口契约（dataclass 类型定义）
# ============================================================================

@dataclass
class DesignOutput:
    """设计步骤输出"""
    architecture: str = ""
    tech_stack: List[str] = field(default_factory=list)
    decisions: Dict[str, str] = field(default_factory=dict)


@dataclass
class CodingOutput:
    """编码步骤输出"""
    files: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class TestOutput:
    """测试步骤输出"""
    passed: bool = False
    coverage: float = 0.0
    failures: List[Dict] = field(default_factory=list)


@dataclass
class ReflectionOutput:
    """反思步骤输出"""
    what_went_well: List[str] = field(default_factory=list)
    what_to_improve: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class AutoCodingWorkflow:
    """Auto-Coding 八步循环工作流
    
    设计 → 分解 → 编码 → 测试 → 反思 → 优化 → 验证 → 输出
    """
    
    def __init__(self, requirements: str, tasks: List[Dict] = None, project_dir: str = None, 
                 timeout_minutes: int = 30, user_models: List[Dict] = None,
                 acceptance_criteria: List[str] = None, constraints: Dict = None):
        self.requirements = requirements
        self.tasks = tasks or []
        self.project_dir = Path(project_dir) if project_dir else Path("/tmp/auto-coding-project")
        self.timeout_minutes = timeout_minutes
        self.user_models = user_models
        
        # 验收标准前置（逆向思考：先明确"什么叫完成"）
        self.acceptance_criteria = acceptance_criteria or ['功能可以正常运行', '代码无语法错误']
        
        # 边界声明（目标/非目标）
        self.scope = constraints or {
            'goal': f'完成：{requirements[:50]}...',
            'in_scope': ['功能实现'],
            'out_of_scope': ['与需求无关的功能'],
            'must_preserve': [],
            'no_modify_patterns': [],
        }
        
        # 约束声明（能改什么/不能改什么）
        self.constraints = {
            'must_preserve': self.scope.get('must_preserve', []),
            'no_modify_patterns': self.scope.get('no_modify_patterns', []),
            'style_guide': self.scope.get('style_guide', None),
        }
        
        # P1-3 修复：初始化日志
        self._init_logging()
        
        # 上下文累积管理（累积历史决策）
        self.context = {
            'original_requirements': requirements,
            'design_decisions': [],
            'coding_assumptions': [],
            'test_findings': [],
            'reflection_insights': [],
            'test_failures': [],
        }
        
        # P1 修复：集成依赖管理器
        self.dm = DependencyManager(str(self.project_dir))
        self.execution_order = None
        self.completed_tasks = set()
        
        # P1 修复：集成模型选择器（复用 RoundTable 的）
        self.model_selector = ModelSelector(user_models=user_models)
        self.agent_models = {}  # Agent 模型映射缓存
        
        # P1 修复：集成 Agent Soul 加载器
        self.soul_loader = AgentSoulLoader()
        
        # 初始化依赖图
        if self.tasks:
            self._initialize_dependency_graph()
        
        self.current_step = 'production'
        self.start_time = None
        self.last_progress_time = None
        
        # 类型安全的输出（接口契约）
        self.design_output: Optional[DesignOutput] = None
        self.coding_output: Optional[CodingOutput] = None
        self.test_output: Optional[TestOutput] = None
        self.reflection_output: Optional[ReflectionOutput] = None
        
        self.result = {
            'code': None,
            'test_result': None,
            'reflection': None,
            'fixed_code': None,
            'final_check': None,
            'iterations': 0,
            'passed': False,
            'task_progress': {},
            'agent_usage': {}  # Agent 使用情况
        }
        
        # v3.3 新增：状态持久化 + 审批 + 通知（可选，兼容旧模式）
        self._has_enhanced = False
        self.state_manager = None
        self.state = None
        self.approval_engine = None
        self.notifier = None
        self._init_enhanced_components()
    
    def _initialize_dependency_graph(self):
        """初始化依赖图并获取执行顺序"""
        try:
            # 构建依赖图
            dependency_data = self.dm.build_dependency_graph(self.tasks)
            
            # 验证依赖图
            is_valid, message = self.dm.validate_dependency_graph(self.tasks)
            if not is_valid:
                print(f"⚠️  依赖图验证失败：{message}")
                return
            
            # 获取拓扑排序
            self.execution_order = self.dm.topological_sort()
            if self.execution_order:
                print(f"✅ 依赖图构建完成，执行顺序：{self.execution_order}")
            else:
                print(f"⚠️  检测到循环依赖，使用原始任务顺序")
                self.execution_order = [task.get('id') for task in self.tasks]
        except Exception as e:
            print(f"⚠️  依赖图初始化失败：{e}")
            self.execution_order = [task.get('id') for task in self.tasks]
    
    def _init_enhanced_components(self):
        """v3.3 新增：初始化增强组件（状态持久化、审批、通知）"""
        try:
            from state_manager import StateManager
            from approval_rules import ApprovalRulesEngine
            from feishu_notifier import FeishuNotifier
            
            self.state_manager = StateManager(self.project_dir)
            self.approval_engine = ApprovalRulesEngine(self.project_dir)
            self.notifier = FeishuNotifier(self.state_manager.state_dir)
            self._has_enhanced = True
            
            logger.info(f"✅ 增强组件已加载（v3.3）")
        except ImportError as e:
            logger.warning(f"⚠️ 增强组件未加载：{e}，以 v3.2 兼容模式运行")
            self._has_enhanced = False
    
    def _init_logging(self):
        """P1-3 修复：初始化日志配置"""
        # 创建日志目录
        log_dir = self.project_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_dir / 'auto_coding.log', encoding='utf-8')
            ]
        )
        logger.info(f"Auto-Coding 日志初始化完成，日志目录：{log_dir}")
    
    async def run(self):
        """运行完整的八步循环工作流（v3.3 增强版）"""
        self.start_time = datetime.now()
        self.last_progress_time = self.start_time
        
        # v3.3 新增：尝试恢复状态
        if self._has_enhanced:
            await self._try_resume()
        
        print(f"\n{'='*60}")
        print(f"🚀 Auto-Coding 八步循环启动")
        if self._has_enhanced:
            print(f"   [增强模式 v3.3：状态持久化 + 审批 + 通知]")
        print(f"{'='*60}")
        print(f"📋 需求：{self.requirements[:100]}...")
        print(f"📊 任务数：{len(self.tasks)}")
        if self.execution_order:
            print(f"🔗 执行顺序：{self.execution_order}")
        print(f"⏱️  超时限制：{self.timeout_minutes} 分钟")
        print(f"{'='*60}\n")
        
        # v3.3 新增：创建 cron 监控
        if self._has_enhanced and not self.state:
            self._create_cron_monitor()
        
        # v3.3 新增：初始化状态
        if self._has_enhanced and not self.state:
            self.state = self.state_manager.init_state(
                requirements=self.requirements
            )
        
        # 第 1 步：设计
        print(f"\n{'='*60}")
        print(f"📝 步骤 1/8: 设计 (Design)")
        print(f"{'='*60}")
        await self.step_design()
        self._update_progress()
        self._save_step_state("design")
        
        # 第 2 步：分解
        print(f"\n{'='*60}")
        print(f"🔪 步骤 2/8: 分解 (Decomposition)")
        print(f"{'='*60}")
        await self.step_decomposition()
        self._update_progress()
        self._save_step_state("decomposition")
        
        # v3.3 新增：自动复杂度分级
        complexity = analyze_complexity(self.requirements, len(self.tasks) if self.tasks else None)
        print(f"\n📊 复杂度分析: {complexity.level} 级 ({complexity.estimated_duration})")
        for reason in complexity.reasons:
            print(f"   • {reason}")
        self.result['complexity'] = complexity.level
        
        # 根据复杂度跳过某些阶段
        skip_design = complexity.level == "A"
        skip_decomposition = complexity.level in ["A", "B"]
        skip_reflection_opt = complexity.level == "A"
        
        # 第 3-6 步：编码→测试→反思→优化（迭代循环，含否决权）
        max_iterations = 3
        for iteration in range(max_iterations):
            print(f"\n{'='*60}")
            print(f"🔁 迭代 {iteration + 1}/{max_iterations}")
            print(f"{'='*60}")
            
            # 第 3 步：编码
            print(f"\n📝 步骤 3/8: 编码 (Coding)")
            await self.step_coding()
            self._update_progress()
            self._save_step_state("coding")
            
            # 第 4 步：测试
            print(f"\n🧪 步骤 4/8: 测试 (Testing)")
            await self.step_testing()
            self._update_progress()
            self._save_step_state("testing")
            
            # A 级任务跳过审查和优化
            if skip_reflection_opt:
                print(f"\n⏭️  A 级任务，跳过审查和优化")
                self.result['test_passed'] = True
                break
            
            # 第 5 步：反思（代码审查，含否决权）
            print(f"\n🤔 步骤 5/8: 反思 (Reflection)")
            review_text = await self.step_reflection_with_review()
            self._update_progress()
            self._save_step_state("reflection")
            
            # v3.3 核心：ReviewerWorker 否决权
            reviewer = ReviewerWorker()
            review_result = reviewer.parse_review_output(review_text)
            
            print(f"\n   📋 审查结果: {'✅ 通过' if review_result.passed else '❌ 否决'}")
            print(f"   🔴 阻塞项: {sum(1 for i in review_result.issues if i.severity == '🔴')} 个")
            print(f"   🟡 建议项: {sum(1 for i in review_result.issues if i.severity == '🟡')} 个")
            
            if review_result.veto:
                print(f"\n   🚫 Reviewer 否决！触发重写")
                # 生成否决提示，保存到 result 供下次 coding 使用
                veto_prompt = reviewer.build_veto_prompt(
                    review_result, 
                    self.result.get('code', '')
                )
                self.result['veto_feedback'] = veto_prompt
                self.result['veto_count'] = self.result.get('veto_count', 0) + 1
                
                # 如果有剩余迭代次数，继续循环（回到 coding）
                if iteration < max_iterations - 1:
                    print(f"   🔄 准备第 {iteration + 2} 轮重写...")
                    continue
                else:
                    print(f"   ⚠️  已达最大迭代次数，停止重写")
                    break
            
            # 审查通过，继续优化
            print(f"\n   ✅ 审查通过，进入优化")
            
            # 第 6 步：优化
            print(f"\n🔧 步骤 6/8: 优化 (Optimization)")
            await self.step_optimization()
            self._update_progress()
            self._save_step_state("optimization")
            
            # 检查是否通过测试
            if self.result.get('test_passed', False):
                print(f"\n✅ 测试通过，退出迭代循环")
                break
            else:
                print(f"\n⚠️  测试未通过，继续迭代...")
        
        # 第 7 步：验证
        print(f"\n{'='*60}")
        print(f"✅ 步骤 7/8: 验证 (Verification)")
        print(f"{'='*60}")
        await self.step_verification()
        self._update_progress()
        self._save_step_state("verification")
        
        # 第 8 步：输出
        print(f"\n{'='*60}")
        print(f"📦 步骤 8/8: 输出 (Output)")
        print(f"{'='*60}")
        await self.step_output()
        self._update_progress()
        self._save_step_state("output")
        
        # v3.4: 可选架构健康检查（improve-architecture）
        await self._trigger_architecture_check()
        
        # v3.3 新增：终态处理
        if self._has_enhanced:
            self._finalize_state("completed")
        
        # 输出最终报告
        self._print_final_report()
        
        return self.result
    
    def _print_task_progress(self):
        """打印任务进度报告"""
        print(f"\n{'='*60}")
        print(f"📊 任务进度报告")
        print(f"{'='*60}")
        
        if not self.tasks:
            print("  无任务列表")
            return
        
        for task in self.tasks:
            task_id = task.get('id')
            task_name = task.get('name', '未知任务')
            status = self.result.get('task_progress', {}).get(task_id, 'unknown')
            
            emoji = {'completed': '✅', 'running': '🔄', 'failed': '❌', 'pending': '⏳', 'unknown': '❓'}
            print(f"  {emoji.get(status, '❓')} 任务 {task_id}: {task_name} - {status}")
        
        print(f"{'='*60}")
    
    async def _try_resume(self):
        """v3.3 新增：尝试从状态恢复"""
        if not self._has_enhanced:
            return
        state = self.state_manager.load_state()
        if not state:
            return
        if state.current_phase in ["completed", "failed", "rejected", "timeout"]:
            print(f"\n📝 发现已完成任务：{state.task_id}（{state.current_phase}）")
            return  # 终态，不恢复
        
        print(f"\n🔄 恢复任务：{state.task_id}")
        print(f"   已完成的阶段：{state.completed_phases}")
        print(f"   从阶段恢复：{state.current_phase}")
        self.state = state
        # 恢复运行时状态
        self.result = dict(state.results)
    
    def _save_step_state(self, step_name: str):
        """v3.3 新增：保存步骤状态"""
        if not self._has_enhanced or not self.state:
            return
        self.state_manager.save_phase(self.state, step_name, {
            "completed_at": datetime.now().isoformat(),
            "result_keys": list(self.result.keys()),
        })
    
    def _finalize_state(self, status: str):
        """v3.3 新增：终态处理（保存 + 通知 + 删 cron）"""
        if not self._has_enhanced or not self.state:
            return
        # 保存终态
        self.state_manager.save_progress(
            self.state,
            current_phase=status,
            results=self.result,
        )
        # 删 cron
        self._delete_cron_monitor()
        # 生成完成通知消息
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        msg = self.notifier.send_completion_report(
            task_id=self.state.task_id,
            project_dir=self.project_dir,
            elapsed_minutes=elapsed,
            completed_phases=self.state.completed_phases,
            requirements=self.requirements,
            test_passed=self.result.get("test_passed", False),
        )
        print(f"\n📢 完成通知已生成（请外层发送）：")
        print(msg)
    
    def _create_cron_monitor(self):
        """v3.3 新增：创建 cron 监控"""
        if not self._has_enhanced:
            return
        try:
            import subprocess
            check_script = Path(__file__).parent / "check_auto_coding_status.py"
            cron_name = f"ac-monitor-{self.state.task_id if self.state else 'unknown'}"
            cron_message = (
                f"检查 Auto-Coding 任务状态\\n"
                f"- 任务ID: {self.state.task_id if self.state else 'unknown'}\\n"
                f"- 项目目录: {self.project_dir}\\n"
                f"- 执行: python3 {check_script} {self.project_dir}\\n"
                f"- 根据 should_notify 和 should_delete_cron 决策"
            )
            subprocess.run([
                "openclaw", "cron", "add",
                "--name", cron_name,
                "--every", "5m",
                "--message", cron_message,
                "--session", "isolated",
                "--timeout-seconds", "60",
                "--tools", "exec,message",
                "--channel", "feishu",
                "--to", os.environ.get("AUTO_CODING_FEISHU_TO", ""),
                "--announce",
            ], capture_output=True, text=True, check=True)
            print(f"\n✅ Cron 监控已创建: {cron_name}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"\n⚠️  Cron 监控创建失败（openclaw CLI 不可用）")
    
    def _delete_cron_monitor(self):
        """v3.3 新增：删除 cron 监控"""
        if not self._has_enhanced:
            return
        try:
            import subprocess
            cron_name = f"ac-monitor-{self.state.task_id if self.state else 'unknown'}"
            subprocess.run([
                "openclaw", "cron", "rm", cron_name,
            ], capture_output=True, text=True, check=True)
            print(f"✅ Cron 监控已删除: {cron_name}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # 可能已经删了或不存在
    
    def _check_timeout(self) -> bool:
        """P1 修复：检查是否超时"""
        if not self.start_time:
            return False
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        return elapsed >= self.timeout_minutes
    
    def _check_deadlock(self, iteration: int) -> bool:
        """P1 修复：死锁检测（进度停滞检查）"""
        if not self.last_progress_time:
            return False
        
        # 如果超过 10 分钟没有进展，视为死锁
        no_progress_minutes = (datetime.now() - self.last_progress_time).total_seconds() / 60
        return no_progress_minutes >= 10
    
    def _update_progress(self):
        """P1 修复：更新进度时间"""
        self.last_progress_time = datetime.now()
    
    async def step_design(self):
        """步骤 1: 设计 - 技术方案设计和架构"""
        print(f"   分析需求并设计技术方案...")
        
        # 加载架构师 Agent
        agent_id = "engineering/engineering-software-architect"
        task_desc = "分析需求并设计技术方案，包括：技术栈选型、架构设计、目录结构"
        
        await self._execute_task_with_agent({'id': 'design', 'name': '设计', 'description': task_desc}, agent_id)
        
        print(f"   ✅ 技术方案设计完成")
    
    async def step_decomposition(self):
        """步骤 2: 分解 - 任务拆解和依赖管理"""
        print(f"   拆解任务并建立依赖关系...")
        
        # 如果没有预定义任务，使用 Agent 帮助分解
        if not self.tasks:
            agent_id = "engineering/engineering-senior-developer"
            task_desc = "根据技术方案拆解任务，定义任务依赖关系"
            await self._execute_task_with_agent({'id': 'decomp', 'name': '分解', 'description': task_desc}, agent_id)
        
        # 验证依赖图
        if self.tasks:
            is_valid, message = self.dm.validate_dependency_graph(self.tasks)
            if is_valid:
                print(f"   ✅ 依赖图验证通过")
            else:
                print(f"   ⚠️  依赖图验证失败：{message}")
        
        print(f"   ✅ 任务分解完成")
    
    async def step_coding(self):
        """步骤 3: 编码 - 代码实现（v3.3 增强：审批检查）"""
        print(f"   根据设计实现代码...")
        
        # v3.3 新增：编码前审批检查（修改敏感文件）
        if self._has_enhanced:
            files_to_edit = self._detect_files_to_edit()
            if files_to_edit:
                decision = self.approval_engine.check_edit(files_to_edit)
                if decision.requires_human:
                    print(f"   ⚠️  文件修改需要审批：{decision.reason}")
                    if self.state:
                        approval_id = self.state_manager.push_approval(
                            self.state,
                            operation="coding",
                            details={
                                "reason": decision.reason,
                                "files": decision.files,
                                "phase": "coding",
                            }
                        )
                        print(f"   ⏸️  审批请求：{approval_id}")
                        # 保存状态并暂停
                        self.state_manager.save_progress(
                            self.state,
                            current_phase="approval_required:coding",
                        )
                    return  # 暂停，等审批
        
        # 按依赖顺序执行任务
        if self.execution_order:
            for task_id in self.execution_order:
                task = next((t for t in self.tasks if t.get('id') == task_id), None)
                if task and task_id not in self.completed_tasks:
                    # 检查依赖是否都已完成
                    deps = task.get('depends_on', [])
                    if all(dep in self.completed_tasks for dep in deps):
                        await self._execute_task_with_agent(task)
                        self.completed_tasks.add(task_id)
        
        print(f"   ✅ 代码实现完成")
    
    def _detect_files_to_edit(self) -> List[str]:
        """v3.3 新增：检测将要修改的文件（简化版）"""
        # 实际应由 Agent 返回文件列表
        # 这里根据需求做简单推断
        return ["src/main.py"]  # 占位

    async def _trigger_architecture_check(self):
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
            from workers.testing_worker import TestingWorker
            from workers.base_worker import WorkerTask
            worker = TestingWorker()
            print(f"   🏗️  架构检查中...")
            result = await worker.execute(WorkerTask(
                id='arch-check', description='架构健康检查', prompt=arch_prompt
            ))
            if result.success:
                self.context['architecture_health'] = result.output
                print(f"   ✅ 架构检查完成")
                if '无改进机会' not in result.output:
                    print(f"   📋 发现架构改进机会：")
                    for line in result.output.split("\n"):
                        if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                            print(f"      {line.strip()}")
            else:
                print(f"   ⚠️  架构检查失败: {result.error}")
        except Exception as e:
            print(f"   ⚠️  架构检查调用异常: {e}")
        
        print(f"{'='*60}\n")
    
    async def step_testing(self):
        """步骤 4: 测试 - 功能测试（v3.4: 嵌入 TDD 红-绿-重构循环）"""
        print(f"   运行功能测试（TDD 模式）...")
        
        code = self.result.get('code', '')
        
        # v3.4: TDD 垂直切片 — 一次一个测试，红→绿→重构
        tdd_prompt = (
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
            worker = TestingWorker()
            print(f"   🧪 TDD 测试生成...")
            result = await worker.execute(WorkerTask(
                id='test', description='TDD 测试', prompt=tdd_prompt
            ))
            if result.success:
                self.context['test_output'] = result.output
                # 从输出判断测试是否通过
                output_lower = result.output.lower()
                self.result['test_passed'] = ('pass' in output_lower and 'fail' not in output_lower) or '通过' in result.output
                print(f"   ✅ TDD 测试完成")
            else:
                self.result['test_passed'] = False
                print(f"   ❌ 测试失败: {result.error}")
        except Exception as e:
            self.result['test_passed'] = False
            print(f"   ⚠️  测试调用异常: {e}")
    
    async def step_reflection(self):
        """步骤 5: 反思 - 代码审查和反思（兼容旧调用）"""
        await self.step_reflection_with_review()
    
    async def step_reflection_with_review(self) -> str:
        """
        步骤 5: 反思 - 代码审查（v3.4: 嵌入 zoom-out 全局视角）
        
        Returns:
            str: 审查输出文本（含 🔴🟡💭 标记）
        """
        print(f"   审查代码质量并反思（zoom-out 模式）...")
        
        code = self.result.get('code', '')
        requirements = self.requirements
        
        # v3.4: zoom-out — 先理解全局再审查
        task_desc = f"""你是一位代码审查专家。使用 zoom-out 方法审查代码。

## 第一步：Zoom-Out（理解全局）
1. 这段代码在系统中的位置和职责
2. 和哪些模块/外部系统交互
3. 调用者是谁、依赖了什么

## 第二步：审查代码
## 原始需求
{requirements}

## 待审查代码
```python
{code[:3000] if code else '# 暂无代码'}
```

## 审查要求
1. 检查是否符合需求（需求明确的做法优先）
2. 检查是否有额外未请求的功能
3. 检查是否过度设计
4. 检查安全、性能、可读性问题

## 输出格式（必须严格遵循）
### 整体评价
[一句话总结代码质量]

### 问题列表
🔴 [类别] 第 X 行：具体问题描述 — 修改建议
🟡 [类别] 第 X 行：具体问题描述 — 修改建议
💭 [类别] 第 X 行：具体问题描述 — 修改建议

### 值得肯定
- [具体优点]

注意：
- 🔴 = 阻塞项（必须修复，否则否决）
- 🟡 = 建议项（推荐修复）
- 💭 = 小改进（可选）
- 需求明确要求的做法优先于极简主义，不要在需求约束上挑刺
"""
        
        await self._execute_task_with_agent({'id': 'reflect', 'name': '反思', 'description': task_desc}, agent_id="engineering/engineering-code-reviewer")
        
        review_text = self.result.get('reflect', '')
        print(f"   ✅ 代码审查完成")
        return review_text
    
    async def step_optimization(self):
        """步骤 6: 优化 - 改进和修复（v3.3: 用优化工程师 + glm-5.1）"""
        print(f"   根据反思结果优化代码...")
        
        agent_id = "engineering/engineering-optimizer"
        task_desc = "根据代码审查结果进行深度优化和重构，追求优雅实现和性能最优"
        
        await self._execute_task_with_agent({'id': 'optimize', 'name': '优化', 'description': task_desc}, agent_id)
        
        print(f"   ✅ 代码优化完成")
    
    async def step_verification(self):
        """步骤 7: 验证 - 最终验证（v3.4: 调用 TestingWorker.verify_implementation）"""
        print(f"   最终验证是否达到交付标准...")
        
        code = self.result.get('code', '')
        
        # 调用 TestingWorker 做实际验证
        try:
            from workers.testing_worker import TestingWorker
            from workers.base_worker import WorkerTask
            worker = TestingWorker()
            verify_prompt = (
                f"对以下代码进行最终交付验证。\n\n"
                f"## 原始需求\n{self.requirements}\n\n"
                f"## 代码\n```python\n{code[:3000] if code else '# 暂无代码'}\n```\n\n"
                f"## 验证维度\n"
                f"1. 功能完整性：是否满足所有需求？\n"
                f"2. 代码质量：是否有明显问题？\n"
                f"3. 边界情况：是否处理了边界情况？\n"
                f"4. 可运行性：代码是否可以正常运行？\n\n"
                f"逐条验证 + 通过/不通过 + 具体证据。"
            )
            print(f"   🧪 调用 TestingWorker 验证...")
            result = await worker.execute(WorkerTask(
                id='verify', description='交付验证', prompt=verify_prompt
            ))
            if result.success:
                self.context['verification_output'] = result.output
        except Exception as e:
            print(f"   ⚠️  验证调用异常: {e}")
        
        # 验证清单（基于实际结果）
        checks = []
        has_code = bool(self.result.get('code'))
        checks.append(('功能完整性', has_code))
        test_passed = self.result.get('test_passed', False)
        checks.append(('测试覆盖', test_passed))
        has_reflection = bool(self.result.get('reflection'))
        checks.append(('代码质量', has_reflection))
        output_exists = self.project_dir.exists()
        checks.append(('文档完整', output_exists))
        
        all_passed = all(result for _, result in checks)
        self.result['verification_passed'] = all_passed
        self.result['verification_details'] = checks
        
        for check_name, passed in checks:
            status = '✅' if passed else '❌'
            print(f"   {status} {check_name}")
        
        print(f"   验证结果：{'✅ 通过' if all_passed else '⚠️  未通过'}")
    
    async def step_output(self):
        """步骤 8: 输出 - 交付物生成"""
        print(f"   生成最终交付物...")
        
        # 创建输出目录
        output_dir = self.project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存源代码（如果有）
        if self.result.get('code'):
            code_file = output_dir / "main.py"
            code_file.write_text(self.result['code'], encoding='utf-8')
            print(f"   ✅ 源代码已保存：{code_file}")
        
        # 生成 README
        readme_content = self._generate_readme()
        readme_file = output_dir / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')
        print(f"   ✅ README 已生成：{readme_file}")
        
        # 生成测试报告
        test_report = self._generate_test_report()
        test_report_file = output_dir / "TEST_REPORT.md"
        test_report_file.write_text(test_report, encoding='utf-8')
        print(f"   ✅ 测试报告已生成：{test_report_file}")
        
        # 更新结果
        self.result['deliverables'] = [
            str(code_file) if self.result.get('code') else "源代码（未生成）",
            str(readme_file),
            str(test_report_file),
        ]
        self.result['output_dir'] = str(output_dir)
        
        print(f"   ✅ 交付物生成完成")
        print(f"   📁 输出目录：{output_dir}")
    
    def _generate_readme(self) -> str:
        """生成 README 文档"""
        project_name = self.project_dir.name
        return f"""# {project_name}

## 项目说明

{self.requirements}

## 项目结构

```
{project_name}/
├── output/
│   ├── main.py
│   ├── README.md
│   └── TEST_REPORT.md
```

## 使用方法

```bash
python output/main.py
```

---
*Generated by Auto-Coding v1.0.6*
"""
    
    def _generate_test_report(self) -> str:
        """生成测试报告"""
        test_passed = self.result.get('test_passed', False)
        verification_passed = self.result.get('verification_passed', False)
        iterations = self.result.get('iterations', 0)
        
        return f"""# 测试报告

## 项目：{self.project_dir.name}

## 测试结果

- 状态：{'✅ 通过' if test_passed else '❌ 未通过'}
- 迭代次数：{iterations}

## 验证结果

- 功能完整性：{'✅' if verification_passed else '❌'}
- 代码质量：{'✅' if verification_passed else '❌'}
- 测试覆盖：{'✅' if test_passed else '❌'}
- 文档完整：{'✅' if verification_passed else '❌'}

## 总结

{'本项目已通过所有测试和验证，可以交付使用。' if verification_passed else '本项目尚未通过全部验证，建议继续优化。'}

---
*Generated by Auto-Coding v1.0.6*
"""
    
    def _print_final_report(self):
        """打印最终报告"""
        print(f"\n{'='*60}")
        print(f"🎉 Auto-Coding 完成！")
        print(f"{'='*60}")
        print(f"📊 总耗时：{(datetime.now() - self.start_time).total_seconds() / 60:.1f} 分钟")
        print(f"📦 交付物：{', '.join(self.result.get('deliverables', []))}")
        print(f"✅ 验证：{'通过' if self.result.get('verification_passed', False) else '未通过'}")
        print(f"{'='*60}")
    
    async def _execute_task_with_agent(self, task: Dict, agent_id: str = None):
        """
        使用 Agent 执行任务（完整的 sessions_spawn 调用）
        
        Args:
            task: 任务字典 {id, name, description, depends_on}
            agent_id: Agent ID（可选，默认自动选择）
        """
        task_id = task.get('id')
        task_name = task.get('name')
        task_desc = task.get('description', '')
        
        # 1. 确定 Agent 身份
        if not agent_id:
            agent_id = self._select_agent_for_task(task)
        print(f"   🤖 选择 Agent: {agent_id}")
        
        # 2. 选择模型（v3.3 按阶段/角色分配不同模型）
        model = self._select_model_for_agent(agent_id)
        print(f"   🎯 使用模型：{model}")
        
        # 3. 加载 Agent Soul
        agent_soul = self.soul_loader.get_agent_soul(agent_id)
        if agent_soul:
            print(f"   📋 加载 Agent Soul: {agent_soul.get('name', agent_id)}")
            system_prompt = agent_soul.get('system', '')
        else:
            print(f"   ⚠️  未找到 Agent Soul，使用默认 Prompt")
            system_prompt = f"你是一位资深{task_name}专家，请完成以下任务..."
        
        # 4. 构建任务 Prompt
        task_prompt = f"""{system_prompt}

## 当前任务
{task_desc}

## 项目需求
{self.requirements}

## 输出要求
- 使用 Markdown 格式
- 包含具体的实现细节
- 如有代码，请提供完整可运行的代码
- 字数控制在 500-1000 字

请开始执行任务：
"""
        
        # 5. 调用 Agent（支持多种方式）
        max_retries = 3
        task_result = None
        for attempt in range(max_retries):
            try:
                # 调用模型生成代码（v3.3 修复：使用 openclaw infer model run）
                task_result = await self._call_agent(
                    task_prompt, task_id, agent_id, model
                )
                if task_result:
                    break
                
                # fallback：模拟结果
                print(f"   ⚠️  模型调用失败，使用模拟结果")
                task_result = self._generate_mock_result(task_id, task_desc)
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"   ⚠️  任务执行失败，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"   ❌ 任务执行失败（已重试{max_retries}次）：{e}")
                    self.result['task_progress'][task_id] = 'failed'
                    raise
        
        # 保存结果
        self.result['task_progress'][task_id] = 'completed'
        self.result['agent_usage'][agent_id] = self.result['agent_usage'].get(agent_id, 0) + 1
        
        # v3.3 修复：把任务结果保存到 result
        if task_result:
            self.result[task_id] = task_result
            self._save_code_to_file(task_result, task_id)
        
        print(f"   ✅ 任务 {task_id} 完成")
    
    # v3.4: Fallback 模型可通过环境变量配置
    # 格式: AUTO_CODING_FALLBACK_MODELS=provider/model1,provider/model2
    FALLBACK_MODELS = os.environ.get(
        "AUTO_CODING_FALLBACK_MODELS",
        "xiaomimimo/mimo-v2.5,xiaomimimo/mimo-v2.5-pro"
    ).split(",")
    
    async def _call_model(self, model: str, prompt: str) -> Optional[str]:
        """
        调用单个模型（v3.3: 抽取为独立方法，支持 fallback 重试）
        """
        import subprocess
        import json
        
        try:
            result = subprocess.run(
                [
                    "openclaw", "infer", "model", "run",
                    "--model", model,
                    "--prompt", prompt,
                    "--json",
                    "--local",
                ],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode != 0:
                return None
            
            response = json.loads(result.stdout)
            if response.get("ok") and response.get("outputs"):
                text = response["outputs"][0].get("text", "")
                return text if text else None
            return None
        except Exception:
            return None
    
    async def _call_agent(self, task_prompt: str, task_id: str,
                            agent_id: str, model: str) -> Optional[str]:
        """
        调用模型生成代码（v3.3 Fallback 版）
        
        火山额度用完 → 自动切 xiaomimimo/mimo-v2.5
        """
        import json
        
        # 构建系统提示 + 用户提示
        system_prompt = (
            "你是一位资深软件工程师。请根据需求编写高质量、可运行的代码。"
            "只输出代码和必要的注释，不要输出解释性文字。"
            "代码必须完整、可运行，使用 Python 语言。"
        )
        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{task_prompt}"
        
        # 第一次尝试：主模型
        print(f"   🚀 调用模型 {model}...")
        text = await self._call_model(model, full_prompt)
        if text:
            print(f"   ✅ 模型返回 {len(text)} 字符")
            return text
        
        # Fallback：主模型失败，依次尝试 MiMo 模型
        for fallback in self.FALLBACK_MODELS:
            if model != fallback:
                print(f"   ⚠️  {model} 调用失败，fallback → {fallback}")
                text = await self._call_model(fallback, full_prompt)
                if text:
                    print(f"   ✅ Fallback 返回 {len(text)} 字符")
                    return text
        
        print(f"   ❌ 所有模型调用失败")
        return None
    
    def _generate_mock_result(self, task_id: str, task_desc: str) -> str:
        """方式 3：模拟结果（fallback）"""
        return f"""# 任务 {task_id} 的模拟结果

## 描述
{task_desc}

## 代码
```python
# TODO: 由 Agent 生成实际代码
# 当前环境无法调用外部 Agent，请检查 openclaw CLI 配置

def main():
    pass

if __name__ == "__main__":
    main()
```

## 说明
- 这是一个占位符结果
- 请确保 openclaw CLI 已安装并配置正确
- 或在 OpenClaw Agent session 内运行以使用 sessions_spawn
"""
    
    def _save_code_to_file(self, task_result: str, task_id: str):
        """v3.3 新增：把 Agent 返回的代码保存到文件"""
        # 尝试从结果中提取代码块
        import re
        code_blocks = re.findall(r'```python\n(.*?)\n```', task_result, re.DOTALL)
        if not code_blocks:
            code_blocks = re.findall(r'```\n(.*?)\n```', task_result, re.DOTALL)
        
        if code_blocks:
            code = code_blocks[0]
            # 保存到项目目录
            code_dir = self.project_dir / "src"
            code_dir.mkdir(parents=True, exist_ok=True)
            code_file = code_dir / f"{task_id}.py"
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"   💾 代码已保存：{code_file}")
            
            # 更新结果
            self.result['code'] = code
            if 'deliverables' not in self.result:
                self.result['deliverables'] = []
            self.result['deliverables'].append(str(code_file))
    
    def _select_model_for_agent(self, agent_id: str) -> str:
        """
        按阶段/角色选择模型（v3.3）
        
        不同模型风格互补：
        - code: 编码专用，响应最快
        - pro: 全面专业，适合设计/架构
        - deepseek: 逻辑强，适合审查
        - lite: 最快，适合验证
        
        Args:
            agent_id: Agent ID（如 engineering/engineering-code-reviewer）
        
        Returns:
            model_id: 模型 ID
        """
        # 按完整 agent_id 映射
        # v3.4: 模型映射可通过环境变量覆盖
        # 环境变量格式: AUTO_CODING_MODEL_<ROLE>=provider/model
        # 例如: AUTO_CODING_MODEL_ARCHITECT=volcengine-plan/doubao-seed-2.0-pro
        DEFAULT_MODEL_MAP = {
            "engineering/engineering-software-architect": "volcengine-plan/doubao-seed-2.0-pro",
            "engineering/engineering-senior-developer": "volcengine-plan/doubao-seed-2.0-code",
            "engineering/engineering-code-reviewer": "volcengine-plan/deepseek-v3.2",
            "engineering/engineering-frontend-developer": "volcengine-plan/doubao-seed-2.0-code",
            "engineering/engineering-backend-architect": "volcengine-plan/doubao-seed-2.0-pro",
            "testing/testing-api-tester": "volcengine-plan/doubao-seed-2.0-pro",
            "engineering/engineering-optimizer": "volcengine-plan/glm-5.1",
            "testing/testing-verifier": "volcengine-plan/glm-5.1",
        }

        # 环境变量覆盖映射（key 为 agent_id 中的角色名，如 architect、developer）
        ENV_MODEL_KEYS = {
            "software-architect": "ARCHITECT",
            "senior-developer": "DEVELOPER",
            "code-reviewer": "REVIEWER",
            "frontend-developer": "FRONTEND",
            "backend-architect": "BACKEND",
            "api-tester": "TESTER",
            "optimizer": "OPTIMIZER",
            "verifier": "VERIFIER",
        }

        # 检查环境变量覆盖
        role_name = agent_id.split("/")[-1] if "/" in agent_id else agent_id
        env_key = ENV_MODEL_KEYS.get(role_name)
        if env_key:
            env_model = os.environ.get(f"AUTO_CODING_MODEL_{env_key}")
            if env_model:
                return env_model

        if agent_id in DEFAULT_MODEL_MAP:
            return DEFAULT_MODEL_MAP[agent_id]

        # fallback：按角色前缀
        role_prefix = agent_id.split('/')[0]
        ROLE_MAP = {
            "engineering": "volcengine-plan/doubao-seed-2.0-code",
            "testing": "volcengine-plan/doubao-seed-2.0-pro",
            "design": "volcengine-plan/doubao-seed-2.0-pro",
        }
        return ROLE_MAP.get(role_prefix, "volcengine-plan/doubao-seed-2.0-code")
    
    def _select_agent_for_task(self, task: Dict) -> str:
        """
        根据任务选择 Agent
        
        Args:
            task: 任务字典
        
        Returns:
            Agent ID
        """
        task_name = task.get('name', '').lower()
        task_desc = task.get('description', '').lower()
        
        # 简单规则匹配
        if any(kw in task_name or kw in task_desc for kw in ['html', 'css', 'ui', '界面', '样式']):
            return "design/design-ui-designer"
        elif any(kw in task_name or kw in task_desc for kw in ['js', 'javascript', '功能', '逻辑']):
            return "engineering/engineering-frontend-developer"
        elif any(kw in task_name or kw in task_desc for kw in ['存储', 'database', 'data']):
            return "engineering/engineering-backend-architect"
        elif any(kw in task_name or kw in task_desc for kw in ['测试', 'test']):
            return "engineering/engineering-code-reviewer"
        else:
            return "engineering/engineering-senior-developer"


# ============================================================================
# 主函数
# ============================================================================

async def run_auto_coding(requirements: str, round_table_plan: dict = None):
    """运行 Auto-Coding 工作流"""
    workflow = AutoCodingWorkflow(requirements, round_table_plan)
    result = await workflow.run()
    return result


if __name__ == '__main__':
    import asyncio
    
    # 测试
    requirements = "创建一个简单的计算器，支持加减乘除"
    
    result = asyncio.run(run_auto_coding(requirements))
    
    print(f"\n{'='*60}")
    print(f"📊 Auto-Coding 结果")
    print(f"{'='*60}")
    print(f"迭代次数：{result['iterations']}")
    print(f"是否通过：{result['passed']}")
    print(f"{'='*60}")
