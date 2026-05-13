#!/usr/bin/env python3
"""
TestingWorker - 测试 Worker（v3.4.1）

负责任务：
1. 测试用例编写
2. 功能验证
3. 问题发现和报告

v3.4.1: 模型完全由 ModelSelector 提供，不硬编码
"""

import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from .base_worker import BaseWorker, WorkerConfig, WorkerTask, WorkerResult


class TestingWorker(BaseWorker):
    """
    Testing Worker

    专门负责测试和验证任务。
    v3.4.1: 模型由 ModelSelector 按 testing 角色动态分配
    """

    ROLE = "testing"  # v3.4.1: 只声明角色，模型由 ModelSelector 提供

    def _default_config(self) -> WorkerConfig:
        """返回默认配置（model 由 BaseWorker __init__ 注入）"""
        return WorkerConfig(
            name="testing",
            model=None,  # v3.4.1: 由 ModelSelector 注入
            model_provider=None,  # v3.4.1: 由 openclaw infer 自动检测
            context_length=131072,
            temperature=0.5,  # 测试用较低温度
            max_tokens=8192,
            timeout_seconds=300,
            retry_count=3,
        )
    
    async def _execute_impl(self, task: WorkerTask) -> str:
        """
        执行测试任务
        
        Args:
            task: WorkerTask 实例
            
        Returns:
            str: 测试结果
        """
        # 1. 构建测试提示词
        prompt = self._build_testing_prompt(task)
        
        # 2. 调用模型
        output = await self.call_model(prompt)
        
        # 3. 分析测试结果
        self._analyze_and_record(output)
        
        return output
    
    def _build_testing_prompt(self, task: WorkerTask) -> str:
        """构建测试的提示词"""
        return f"""# 测试任务

## 任务描述
{task.description}

## 测试需求
{task.prompt}

## 上下文
{task.context}

## 测试要求
1. 编写完整的测试用例
2. 覆盖正常路径和边界情况
3. 提供清晰的测试结果报告
4. 如发现问题，详细描述

请执行测试：
"""
    
    def _analyze_and_record(self, output: str) -> None:
        """分析测试结果并记录到 scratchpad"""
        if not self.scratchpad:
            return
        
        # 简单分析输出
        output_lower = output.lower()
        
        if "pass" in output_lower and "fail" not in output_lower:
            severity = "info"
            title = "测试通过"
        elif "fail" in output_lower:
            severity = "major"
            title = "测试发现问题"
        elif "error" in output_lower or "exception" in output_lower:
            severity = "critical"
            title = "测试执行异常"
        else:
            severity = "info"
            title = "测试完成"
        
        self.scratchpad.add_test_finding(
            title=title,
            content=output[:1000],
            severity=severity,
            tags=["testing", "automated"]
        )
    
    def _record_specific(self, task: WorkerTask, result: WorkerResult) -> None:
        """Testing Worker 特有的 scratchpad 记录"""
        if not self.scratchpad:
            return
        
        # 测试结果已经在 _analyze_and_record 中记录
        pass
    
    async def run_tests(self, code: str, test_cases: List[Dict] = None) -> str:
        """
        运行测试
        
        Args:
            code: 待测试的代码
            test_cases: 测试用例列表（可选）
            
        Returns:
            str: 测试结果报告
        """
        if test_cases is None:
            test_cases = [
                {"input": "1 + 1", "expected": "2"},
                {"input": "10 - 5", "expected": "5"},
                {"input": "3 * 4", "expected": "12"},
                {"input": "10 / 2", "expected": "5"},
            ]
        
        test_cases_text = "\n".join([
            f"- 输入: {tc['input']}, 期望: {tc['expected']}"
            for tc in test_cases
        ])
        
        prompt = f"""# 功能测试

## 待测试代码
```python
{code}
```

## 测试用例
{test_cases_text}

## 要求
1. 逐个执行测试用例
2. 记录实际输出和期望输出
3. 判断是否通过
4. 给出总结

请执行测试：
"""
        
        return await self.call_model(prompt)
    
    async def verify_implementation(self, requirements: str, code: str) -> str:
        """
        验证实现是否满足需求
        
        Args:
            requirements: 原始需求
            code: 实现的代码
            
        Returns:
            str: 验证结果
        """
        prompt = f"""# 实现验证

## 原始需求
{requirements}

## 实现代码
```python
{code}
```

## 验证维度
1. **功能完整性**: 是否满足所有需求？
2. **代码质量**: 是否有明显问题？
3. **边界情况**: 是否处理了边界情况？
4. **可运行性**: 代码是否可以正常运行？

## 输出格式
```
## 验证结果
[通过/部分通过/未通过]

## 详细分析
[逐项分析]

## 问题列表
[如有发现问题]
```

请执行验证：
"""
        
        return await self.call_model(prompt)
    
    async def regression_test(self, old_code: str, new_code: str, 
                               test_suite: str) -> str:
        """
        回归测试 - 验证修改没有破坏现有功能
        
        Args:
            old_code: 旧版本代码
            new_code: 新版本代码
            test_suite: 测试套件
            
        Returns:
            str: 回归测试结果
        """
        prompt = f"""# 回归测试

## 旧版本代码
```python
{old_code}
```

## 新版本代码
```python
{new_code}
```

## 测试套件
{test_suite}

## 要求
1. 使用相同的测试用例测试新旧代码
2. 对比结果，确保新版本没有破坏现有功能
3. 检查性能变化
4. 给出详细的回归测试报告

请执行回归测试：
"""
        
        return await self.call_model(prompt)
    
    async def generate_test_cases(self, code: str, coverage: str = "normal") -> str:
        """
        根据代码生成测试用例
        
        Args:
            code: 待测试的代码
            coverage: 覆盖级别 (normal | thorough)
            
        Returns:
            str: 生成的测试用例
        """
        coverage_req = "正常路径和边界情况" if coverage == "normal" else "包括异常情况和负面测试"
        
        prompt = f"""# 测试用例生成

## 待测试代码
```python
{code}
```

## 覆盖要求
{coverage_req}

## 要求
1. 生成完整的测试用例
2. 每个测试用例包含：输入、期望输出、测试目的
3. 使用 pytest 格式
4. 包含必要的 setup/teardown

请生成测试用例：
"""
        
        return await self.call_model(prompt)


if __name__ == "__main__":
    # 测试 TestingWorker
    print("=" * 60)
    print("TestingWorker 测试")
    print("=" * 60)
    
    async def main():
        worker = TestingWorker()
        
        task = WorkerTask(
            id="test-001",
            description="验证计算器功能",
            prompt="测试计算器的加减乘除功能",
            context="计算器使用 Python 实现",
        )
        
        result = await worker.execute(task)
        
        print(f"\n任务结果:")
        print(f"  成功: {result.success}")
        print(f"  输出长度: {len(result.output)} 字符")
        print(f"  耗时: {result.duration_seconds:.1f}s")
        print(f"\n输出预览:")
        print(result.output[:500])
    
    asyncio.run(main())
