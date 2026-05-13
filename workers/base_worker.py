#!/usr/bin/env python3
"""
BaseWorker - Worker 基类

定义 Worker 的通用接口和功能，所有具体 Worker 都应继承此类。
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class WorkerConfig:
    """Worker 配置"""
    name: str                    # Worker 名称
    model: str                   # 使用的模型
    model_provider: str          # 模型提供商
    context_length: int          # 上下文长度
    temperature: float = 0.7      # 生成温度
    max_tokens: int = 8192       # 最大 token 数
    timeout_seconds: int = 300   # 超时时间
    retry_count: int = 3         # 重试次数


@dataclass
class WorkerTask:
    """Worker 任务"""
    id: str                      # 任务 ID
    description: str             # 任务描述
    prompt: str                  # 输入提示
    context: str = ""             # 额外上下文
    dependencies: List[str] = field(default_factory=list)


@dataclass
class WorkerResult:
    """Worker 执行结果"""
    task_id: str
    success: bool
    output: str
    error: str = ""
    duration_seconds: float = 0
    tokens_used: int = 0
    model: str = ""


class BaseWorker(ABC):
    """
    Worker 基类
    
    所有具体 Worker 都应继承此类并实现抽象方法。
    
    属性：
    - config: Worker 配置
    - scratchpad: 共享的 scratchpad 管理器（可选）
    """
    
    # 默认配置（子类应覆盖）
    # v3.4.1: Worker 不硬编码任何模型，只声明 ROLE，模型完全由 ModelSelector 提供
    ROLE = "general"  # 子类覆盖：engineering/testing/reviewer 等
    DEFAULT_TIMEOUT = 300
    
    def __init__(self, config: WorkerConfig = None, scratchpad=None, model_selector=None, model_override: str = None):
        """
        初始化 Worker
        
        Args:
            config: Worker 配置（可选）
            scratchpad: ScratchpadManager 实例（可选，用于跨 Worker 共享）
            model_selector: ModelSelector 实例（必须，v3.4.1 不允许 Worker 自己选模型）
            model_override: 外部指定的模型（可选，优先级最高，来自 workflow phase 配置）
        """
        # v3.4.1: 必须通过 ModelSelector 获取模型，禁止 Worker 内部硬编码
        if model_selector is None:
            from model_selector import get_model_selector
            model_selector = get_model_selector()
        self.model_selector = model_selector
        
        # 模型选择优先级：model_override > ModelSelector 按 role 分配 > 错误
        if model_override:
            selected_model = model_override
        else:
            selected_model = model_selector.select_model_for_role(self.ROLE)
        
        if not selected_model:
            raise RuntimeError(
                f"❌ Worker 初始化失败：{self.ROLE} 角色无可用模型。\n"
                f"请配置至少一个 provider，或检查 ModelSelector 降级链路。"
            )
        
        # 如果 config 没指定 model，用上面的选择结果
        if config is None:
            config = self._default_config()
        if not config.model:
            config = config._replace(model=selected_model)
        
        self.config = config
        self.scratchpad = scratchpad
        self._setup_directories()
    
    @abstractmethod
    def _default_config(self) -> WorkerConfig:
        """返回默认配置（子类实现）"""
        pass
    
    def _setup_directories(self) -> None:
        """设置工作目录"""
        self.work_dir = Path(f"/tmp/auto-coding-projects/workers/{self.config.name}")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志目录
        self.log_dir = self.work_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, task: WorkerTask) -> WorkerResult:
        """
        执行任务（主入口）
        
        Args:
            task: WorkerTask 实例
            
        Returns:
            WorkerResult: 执行结果
        """
        start_time = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"👷 [{self.config.name}] 执行任务: {task.id}")
        print(f"{'='*60}")
        print(f"   模型: {self.config.model}")
        print(f"   描述: {task.description[:50]}...")
        print(f"{'='*60}")
        
        # 重试循环
        last_error = ""
        for attempt in range(self.config.retry_count):
            try:
                # 调用子类的实现
                output = await self._execute_impl(task)
                
                duration = (datetime.now() - start_time).total_seconds()
                
                result = WorkerResult(
                    task_id=task.id,
                    success=True,
                    output=output,
                    duration_seconds=duration,
                    model=self.config.model,
                )
                
                # 记录到 scratchpad
                if self.scratchpad:
                    self._record_to_scratchpad(task, result)
                
                print(f"\n✅ [{self.config.name}] 任务 {task.id} 完成")
                print(f"   耗时: {duration:.1f}s")
                
                return result
                
            except Exception as e:
                last_error = str(e)
                wait_time = 2 ** attempt  # 指数退避：2s -> 4s -> 8s
                
                # 记录重试状态
                if self.scratchpad:
                    self.scratchpad.save_current_task(
                        stage="retry",
                        step=f"任务 {task.id} 重试",
                        task_status="running",
                        retry_count=attempt + 1,
                        error=str(e),
                    )
                
                print(f"⚠️  任务执行失败 (尝试 {attempt + 1}/{self.config.retry_count}): {e}")
                
                if attempt < self.config.retry_count - 1:
                    print(f"   {wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"   ❌ 已达重试上限 ({self.config.retry_count} 次)，放弃重试")
        
        # 所有重试都失败
        duration = (datetime.now() - start_time).total_seconds()
        result = WorkerResult(
            task_id=task.id,
            success=False,
            output="",
            error=last_error,
            duration_seconds=duration,
            model=self.config.model,
        )
        
        print(f"\n❌ [{self.config.name}] 任务 {task.id} 失败: {last_error}")
        
        return result
    
    @abstractmethod
    async def _execute_impl(self, task: WorkerTask) -> str:
        """
        实际执行逻辑（子类实现）
        
        Args:
            task: WorkerTask 实例
            
        Returns:
            str: 执行输出
        """
        pass
    
    def _record_to_scratchpad(self, task: WorkerTask, result: WorkerResult) -> None:
        """记录执行结果到 scratchpad"""
        if not self.scratchpad:
            return
        
        # 不同的 Worker 记录不同的内容
        if hasattr(self, '_record_specific'):
            self._record_specific(task, result)
    
    def _load_prompt_template(self, template_name: str) -> str:
        """
        加载提示词模板
        
        Args:
            template_name: 模板名称
            
        Returns:
            str: 模板内容
        """
        # 尝试从 skills/auto-coding-v2/prompts/ 加载
        prompt_path = Path(__file__).parent.parent / "prompts" / f"{template_name}.md"
        
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        
        return ""
    
    async def call_model(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """
        调用模型（v3.3 修复版）
        
        使用 openclaw infer model run --json --local 调用火山引擎 API
        
        Args:
            prompt: 用户提示
            system: 系统提示（可选）
            temperature: 温度参数（可选）
            max_tokens: 最大 token 数（可选）
            
        Returns:
            str: 模型响应
        """
        import subprocess
        import json
        
        model = self.config.model  # v3.4.1: __init__ 已通过 ModelSelector 保证有值
        full_prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}" if system else prompt
        
        try:
            result = subprocess.run(
                [
                    "openclaw", "infer", "model", "run",
                    "--model", model,
                    "--prompt", full_prompt,
                    "--json",
                    "--local",
                ],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode != 0:
                return f"[模型调用失败] {result.stderr[:200]}"
            
            try:
                response = json.loads(result.stdout)
                if response.get("ok") and response.get("outputs"):
                    return response["outputs"][0].get("text", "")
                return f"[模型返回空结果] {result.stdout[:200]}"
            except json.JSONDecodeError:
                return result.stdout
                
        except Exception as e:
            return f"[调用异常] {str(e)}"

    
    async def batch_execute(self, tasks: List[WorkerTask]) -> List[WorkerResult]:
        """
        批量执行任务
        
        Args:
            tasks: 任务列表
            
        Returns:
            List[WorkerResult]: 结果列表
        """
        results = []
        
        for task in tasks:
            # 等待任务完成（串行执行）
            result = await self.execute(task)
            results.append(result)
            
            # 如果失败且有关键依赖，不继续
            if not result.success and task.dependencies:
                remaining = [t for t in tasks if t.id not in [r.task_id for r in results]]
                for t in remaining:
                    results.append(WorkerResult(
                        task_id=t.id,
                        success=False,
                        output="",
                        error=f"依赖任务失败，跳过"
                    ))
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取 Worker 统计信息"""
        return {
            "name": self.config.name,
            "model": self.config.model,
            "work_dir": str(self.work_dir),
        }


# ============================================================================
# 辅助函数
# ============================================================================

def create_worker(worker_type: str, **kwargs) -> BaseWorker:
    """
    工厂函数：创建 Worker 实例
    
    Args:
        worker_type: Worker 类型 ("engineering" | "testing")
        **kwargs: 传递给 Worker 的其他参数
        
    Returns:
        BaseWorker: Worker 实例
    """
    from .engineering_worker import EngineeringWorker
    from .testing_worker import TestingWorker
    
    if worker_type == "engineering":
        return EngineeringWorker(**kwargs)
    elif worker_type == "testing":
        return TestingWorker(**kwargs)
    else:
        raise ValueError(f"Unknown worker type: {worker_type}")


if __name__ == "__main__":
    # 测试 BaseWorker
    print("=" * 60)
    print("BaseWorker 测试")
    print("=" * 60)
    
    class DummyWorker(BaseWorker):
        def _default_config(self) -> WorkerConfig:
            return WorkerConfig(
                name="dummy",
                model="minimax/MiniMax-M2.7",
                model_provider="MiniMax",
                context_length=192000,
            )
        
        async def _execute_impl(self, task: WorkerTask) -> str:
            await asyncio.sleep(0.5)  # 模拟工作
            return f"Dummy result for: {task.description}"
    
    async def main():
        worker = DummyWorker()
        
        task = WorkerTask(
            id="test-001",
            description="测试任务",
            prompt="执行测试"
        )
        
        result = await worker.execute(task)
        
        print(f"\n结果: {result.success}")
        print(f"输出: {result.output[:100]}")
    
    asyncio.run(main())
