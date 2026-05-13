#!/usr/bin/env python3
"""
ComplexityAnalyzer - 任务复杂度自动分级器（v3.3）

自动判断需求复杂度（A/B/C），决定走哪个流程。

分级规则：
- A (Micro)：单函数 / Bug 修复 / 配置修改
- B (Feature)：模块开发 / 新 API / 组件开发
- C (System)：完整系统 / 架构设计 / 多模块项目
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ComplexityResult:
    """复杂度分析结果"""
    level: str                    # A / B / C
    score: int                    # 0-100 复杂度分数
    reasons: list                 # 判定理由
    estimated_duration: str         # 预估耗时
    recommended_phases: list        # 推荐阶段列表


class ComplexityAnalyzer:
    """
    任务复杂度分析器
    
    基于需求文本特征自动判断复杂度等级。
    """

    # A 级关键词（简单单一功能）
    A_KEYWORDS = [
        "写一个函数", "写一个方法", "修复", "bug", "改", "调整", "配置",
        "简单", "单函数", "单行", "一行代码", "加个", "改成",
        "format", "rename", "refactor 小", "typo", "拼写",
    ]
    
    # C 级关键词（复杂系统）
    C_KEYWORDS = [
        "系统", "平台", "架构", "框架", "重构", "从零搭建",
        "完整", "全套", "全套方案", "整体", "全面",
        "多模块", "多页面", "多角色", "微服务", "分布式",
        "数据库设计", "ER 图", "API 设计", "接口设计",
        "用户系统", "权限系统", "支付系统", "订单系统",
    ]
    
    # B 级关键词（中等模块）
    B_KEYWORDS = [
        "模块", "功能", "页面", "组件", "API", "接口",
        "CRUD", "增删改查", "列表", "详情", "表单",
        "登录", "注册", "搜索", "筛选", "排序",
        "导入", "导出", "上传", "下载",
    ]

    def __init__(self):
        pass

    def analyze(self, requirements: str, task_count: Optional[int] = None) -> ComplexityResult:
        """
        分析需求复杂度
        
        Args:
            requirements: 需求描述文本
            task_count: 预定义任务数量（如有）
        
        Returns:
            ComplexityResult
        """
        text = requirements.lower()
        score = 0
        reasons = []
        
        # 1. 文本长度打分
        length = len(requirements)
        if length < 100:
            score -= 10
            reasons.append(f"需求简短 ({length} 字)")
        elif length > 500:
            score += 20
            reasons.append(f"需求较长 ({length} 字)")
        elif length > 1000:
            score += 40
            reasons.append(f"需求很长 ({length} 字)")
        
        # 2. 关键词匹配
        a_matches = sum(1 for kw in self.A_KEYWORDS if kw in text)
        b_matches = sum(1 for kw in self.B_KEYWORDS if kw in text)
        c_matches = sum(1 for kw in self.C_KEYWORDS if kw in text)
        
        if a_matches > 0:
            score -= a_matches * 15
            reasons.append(f"检测到 {a_matches} 个简单任务关键词")
        
        if b_matches > 0:
            score += b_matches * 10
            reasons.append(f"检测到 {b_matches} 个模块级关键词")
        
        if c_matches > 0:
            score += c_matches * 25
            reasons.append(f"检测到 {c_matches} 个系统级关键词")
        
        # 3. 任务数量（如果提供了）
        if task_count is not None:
            if task_count == 1:
                score -= 15
                reasons.append("单任务")
            elif task_count <= 3:
                score += 5
                reasons.append(f"少量任务 ({task_count} 个)")
            elif task_count > 5:
                score += 30
                reasons.append(f"多任务 ({task_count} 个)")
        
        # 4. 特殊模式检测
        # 多个"功能"、"模块"出现 → B/C
        feature_count = len(re.findall(r"功能|模块|页面|组件", text))
        if feature_count >= 3:
            score += 15
            reasons.append(f"涉及 {feature_count} 个功能点")
        
        # 有技术栈指定 → 可能是系统级
        tech_stack = re.search(r"技术栈|tech stack|使用|用.*实现", text)
        if tech_stack:
            score += 10
            reasons.append("指定了技术栈")
        
        # 有验收标准/验收条件 → 可能是复杂项目
        acceptance = re.search(r"验收|标准|条件|acceptance|criteria", text)
        if acceptance:
            score += 10
            reasons.append("包含验收标准")
        
        # 5. 最终判定
        if score <= 0:
            level = "A"
            duration = "1-3 分钟"
            phases = ["coding", "testing", "verification"]
        elif score <= 35:
            level = "B"
            duration = "5-15 分钟"
            phases = ["design", "coding", "testing", "verification"]
        else:
            level = "C"
            duration = "15-30 分钟"
            phases = ["design", "decomposition", "coding", "testing", "reflection", "optimization", "verification"]
        
        return ComplexityResult(
            level=level,
            score=max(0, min(100, score + 50)),  # 映射到 0-100
            reasons=reasons,
            estimated_duration=duration,
            recommended_phases=phases
        )

    def format_result(self, result: ComplexityResult) -> str:
        """格式化输出"""
        lines = [
            f"## 复杂度分析结果",
            f"",
            f"**等级**: {result.level} ({'简单' if result.level == 'A' else ('中等' if result.level == 'B' else '复杂')})",
            f"**分数**: {result.score}/100",
            f"**预估耗时**: {result.estimated_duration}",
            f"**推荐流程**: {' → '.join(result.recommended_phases)}",
            f"",
            f"### 判定理由",
        ]
        for r in result.reasons:
            lines.append(f"- {r}")
        return "\n".join(lines)


# 快捷函数
def analyze_complexity(requirements: str, task_count: Optional[int] = None) -> ComplexityResult:
    """快捷分析"""
    analyzer = ComplexityAnalyzer()
    return analyzer.analyze(requirements, task_count)


# 测试
if __name__ == "__main__":
    print("🧪 ComplexityAnalyzer 测试")
    print("="*60)
    
    test_cases = [
        ("写一个计算斐波那契数列的 Python 函数", None, "A"),
        ("实现用户登录功能，包括前端表单和后端 JWT 验证", None, "B"),
        ("从零搭建一个完整的电商后台管理系统，包含商品管理、订单管理、用户权限、支付对接", None, "C"),
    ]
    
    for req, tc, expected in test_cases:
        result = analyze_complexity(req, tc)
        status = "✅" if result.level == expected else "❌"
        print(f"{status} 预期 {expected}，实际 {result.level} | {req[:40]}...")
        print(f"   分数: {result.score} | 耗时: {result.estimated_duration}")
        print()
    
    print("="*60)
