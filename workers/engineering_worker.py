#!/usr/bin/env python3
"""
EngineeringWorker - 工程 Worker（v3.4.1）

负责任务：
1. 代码生成和实现
2. 代码优化和重构
3. 修复 Bug 和问题

v3.4.1: 模型完全由 ModelSelector 提供，不硬编码
"""

import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from .base_worker import BaseWorker, WorkerConfig, WorkerTask, WorkerResult


class EngineeringWorker(BaseWorker):
    """
    Engineering Worker

    专门负责代码实现和优化任务。
    v3.4.1: 模型由 ModelSelector 按 engineering 角色动态分配
    """

    ROLE = "engineering"  # v3.4.1: 只声明角色，模型由 ModelSelector 提供

    def _default_config(self) -> WorkerConfig:
        """返回默认配置（model 由 BaseWorker __init__ 注入）"""
        return WorkerConfig(
            name="engineering",
            model=None,  # v3.4.1: 由 ModelSelector 注入
            model_provider=None,  # v3.4.1: 由 openclaw infer 自动检测
            context_length=131072,
            temperature=0.7,
            max_tokens=8192,
            timeout_seconds=300,
            retry_count=3,
        )
    
    async def _execute_impl(self, task: WorkerTask) -> str:
        """
        执行代码实现任务
        
        Args:
            task: WorkerTask 实例
            
        Returns:
            str: 生成的代码
        """
        # 1. 构建提示词
        prompt = self._build_coding_prompt(task)
        
        # 2. 调用模型生成代码
        output = await self.call_model(prompt)
        
        # 3. 保存生成的代码
        self._save_generated_code(task, output)
        
        return output
    
    def _build_coding_prompt(self, task: WorkerTask) -> str:
        """构建代码生成的提示词"""
        # 加载模板（如果存在）
        template = self._load_prompt_template("worker_engineering")
        
        if template:
            # 填充模板
            return template.format(
                task_description=task.description,
                prompt=task.prompt,
                context=task.context,
            )
        
        # 默认提示词
        return f"""# 代码实现任务

## 任务描述
{task.description}

## 详细需求
{task.prompt}

## 上下文
{task.context}

## 要求
1. 给出完整可运行的代码
2. 包含必要的注释和文档字符串
3. 确保代码质量
4. 如需要，提供多个文件

请开始实现：
"""
    
    def _save_generated_code(self, task: WorkerTask, output: str) -> None:
        """保存生成的代码"""
        # 创建输出目录
        output_dir = self.work_dir / task.id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 尝试解析代码块
        import re
        
        # 提取 markdown 代码块
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', output, re.DOTALL)
        
        if code_blocks:
            # 保存第一个代码块作为 main.py
            main_file = output_dir / "main.py"
            main_file.write_text(code_blocks[0], encoding="utf-8")
            
            # 保存完整输出
            full_output = output_dir / "full_output.md"
            full_output.write_text(output, encoding="utf-8")
        else:
            # 没有代码块，保存完整输出
            full_output = output_dir / "output.md"
            full_output.write_text(output, encoding="utf-8")
    
    def _record_specific(self, task: WorkerTask, result: WorkerResult) -> None:
        """Engineering Worker 特有的 scratchpad 记录"""
        if not self.scratchpad:
            return
        
        # 记录代码片段
        import re
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', result.output, re.DOTALL)
        
        if code_blocks:
            self.scratchpad.add_code_snippet(
                title=f"Engineering: {task.description[:50]}",
                code=code_blocks[0][:1000],  # 限制长度
                language="python",
                description=f"任务 {task.id} 生成的代码",
                tags=["engineering", task.id]
            )
    
    async def fix_issues(self, issues: List[Dict], context: str = "") -> str:
        """
        修复问题
        
        Args:
            issues: 问题列表，每个问题包含 title 和 content
            context: 额外上下文
            
        Returns:
            str: 修复后的代码
        """
        issues_text = "\n".join([
            f"- **{issue['title']}**: {issue['content']}"
            for issue in issues
        ])
        
        prompt = f"""# 问题修复任务

## 需要修复的问题
{issues_text}

## 上下文
{context}

## 要求
1. 逐一修复每个问题
2. 保持代码风格一致
3. 确保修复不引入新问题
4. 给出完整可运行的代码

请执行修复：
"""
        
        return await self.call_model(prompt)
    
    async def optimize_code(self, code: str, goal: str = "performance") -> str:
        """
        优化代码
        
        Args:
            code: 待优化的代码
            goal: 优化目标 (performance | readability | both)
            
        Returns:
            str: 优化后的代码
        """
        prompt = f"""# 代码优化任务

## 待优化代码
```{self._detect_language(code)}
{code}
```

## 优化目标
{goal}

## 要求
1. 在保持功能不变的前提下优化
2. 解释优化点
3. 给出优化后的完整代码

请执行优化：
"""
        
        return await self.call_model(prompt)
    
    def _detect_language(self, code: str) -> str:
        """简单检测代码语言"""
        if "def " in code and ":" in code:
            return "python"
        elif "function" in code or "const " in code or "let " in code:
            return "javascript"
        elif "public class" in code or "private void" in code:
            return "java"
        elif "#include" in code:
            return "cpp"
        return "text"
    
    async def refactor(self, code: str, target_style: str = "clean") -> str:
        """
        重构代码
        
        Args:
            code: 待重构的代码
            target_style: 目标风格 (clean | functional | oop)
            
        Returns:
            str: 重构后的代码
        """
        prompt = f"""# 代码重构任务

## 待重构代码
```{self._detect_language(code)}
{code}
```

## 目标风格
{target_style}

## 要求
1. 改进代码结构，但不改变功能
2. 提高可读性和可维护性
3. 给出重构后的完整代码
4. 解释主要改动

请执行重构：
"""
        
        return await self.call_model(prompt)


if __name__ == "__main__":
    # 测试 EngineeringWorker
    print("=" * 60)
    print("EngineeringWorker 测试")
    print("=" * 60)
    
    async def main():
        worker = EngineeringWorker()
        
        task = WorkerTask(
            id="eng-001",
            description="实现简单计算器",
            prompt="实现一个简单的计算器，支持加减乘除运算",
            context="使用 Python 语言",
        )
        
        result = await worker.execute(task)
        
        print(f"\n任务结果:")
        print(f"  成功: {result.success}")
        print(f"  输出长度: {len(result.output)} 字符")
        print(f"  耗时: {result.duration_seconds:.1f}s")
        print(f"\n输出预览:")
        print(result.output[:500])
    
    asyncio.run(main())
