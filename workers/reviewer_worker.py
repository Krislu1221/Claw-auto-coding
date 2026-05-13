#!/usr/bin/env python3
"""
ReviewerWorker - 代码审查 Worker（v3.3）

核心能力：
1. 代码质量审查（反模式、安全、过度设计）
2. 阻塞项检测（🔴 级别问题 → 否决）
3. 建设性反馈（🟡 建议项、💭 小改进）

否决权机制：
- 发现 🔴 阻塞项 → 返回 veto=True，强制触发重写
- 只有 🟡/💭 → 返回 veto=False，继续流程
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ReviewIssue:
    """审查发现的问题"""
    severity: str          # 🔴 阻塞 / 🟡 建议 / 💭 小改进
    category: str          # 安全/性能/可读性/过度设计/边界/其他
    line: Optional[int]    # 行号（如有）
    description: str       # 问题描述
    suggestion: str        # 修改建议


@dataclass
class ReviewResult:
    """审查结果"""
    passed: bool                      # 是否通过（无 🔴 阻塞项）
    veto: bool                        # 是否否决（有 🔴 阻塞项）
    issues: List[ReviewIssue] = field(default_factory=list)
    summary: str = ""                 # 整体评价
    praise: List[str] = field(default_factory=list)  # 值得肯定的地方


class ReviewerWorker:
    """
    Reviewer Worker - 代码审查专家
    
    使用模型：volcengine-plan/deepseek-v3.2
    核心约束：审查边界（需求明确的做法优先于极简主义）
    """

    # 严重级别映射
    SEVERITY_ORDER = {"🔴": 3, "🟡": 2, "💭": 1}
    CRITICAL_EMOJIS = ["🔴", "❌", "CRITICAL", "BLOCKING", "严重", "阻塞"]

    def __init__(self):
        # 注意：实际审查模型由 auto_coding_workflow._get_agent_model() 决定
        # 此处仅保留默认值作为参考
        self.model = "volcengine-plan/deepseek-v3.2"

    def parse_review_output(self, raw_text: str) -> ReviewResult:
        """
        解析 Reviewer 返回的审查文本，提取结构化结果
        
        预期格式：
        ## 整体评价
        ...
        
        ## 问题列表
        🔴 [安全] 第 42 行：SQL 注入风险 — 建议用参数化查询
        🟡 [性能] 第 55 行：循环里查数据库 — 建议批量查询
        💭 [可读性] 第 10 行：变量名太短 — 建议用描述性命名
        
        ## 值得肯定
        - ...
        """
        issues = []
        praise = []
        summary = ""
        
        # 1. 提取整体评价
        summary_match = re.search(r"##?\s*(?:整体评价|总结|Summary)\s*\n(.*?)(?=##?\s|$)", raw_text, re.DOTALL | re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).strip()
        
        # 2. 提取问题列表
        # 匹配行格式：🔴/🟡/💭 [类别] 描述 — 建议...
        issue_pattern = re.compile(
            r"^(🔴|🟡|💭)\s*\[(.*?)\]\s*(.*?)(?:\s*[—-]\s*(.*))?$",
            re.MULTILINE
        )
        for match in issue_pattern.finditer(raw_text):
            severity = match.group(1)
            category = match.group(2).strip()
            description = match.group(3).strip()
            suggestion = match.group(4).strip() if match.group(4) else ""
            
            # 尝试提取行号
            line_match = re.search(r"第?\s*(\d+)\s*行", description)
            line = int(line_match.group(1)) if line_match else None
            
            issues.append(ReviewIssue(
                severity=severity,
                category=category,
                line=line,
                description=description,
                suggestion=suggestion
            ))
        
        # 3. 提取值得肯定的地方
        praise_section = re.search(r"##?\s*(?:值得肯定|表扬|Good|优点)\s*\n(.*?)(?=##?\s|$)", raw_text, re.DOTALL | re.IGNORECASE)
        if praise_section:
            praise_text = praise_section.group(1)
            praise = [p.strip().lstrip("-• ") for p in praise_text.split("\n") if p.strip()]
        
        # 4. 判断否决（有 🔴 阻塞项 → 否决）
        has_critical = any(i.severity in ["🔴"] for i in issues)
        
        return ReviewResult(
            passed=not has_critical,
            veto=has_critical,
            issues=issues,
            summary=summary,
            praise=praise
        )

    def build_veto_prompt(self, review_result: ReviewResult, code: str) -> str:
        """
        当 Reviewer 否决时，生成返回给 EngineeringWorker 的重写提示
        
        包含：
        - 阻塞项清单（必须修复）
        - 建议项清单（推荐修复）
        - 原代码片段
        """
        critical_issues = [i for i in review_result.issues if i.severity == "🔴"]
        suggestion_issues = [i for i in review_result.issues if i.severity in ["🟡", "💭"]]
        
        prompt = "## 代码审查反馈（需重写）\n\n"
        prompt += f"{review_result.summary}\n\n"
        
        if critical_issues:
            prompt += "### 🔴 阻塞项（必须修复）\n"
            for idx, issue in enumerate(critical_issues, 1):
                line_info = f"第 {issue.line} 行" if issue.line else ""
                prompt += f"{idx}. [{issue.category}] {line_info}：{issue.description}\n"
                if issue.suggestion:
                    prompt += f"   → 建议：{issue.suggestion}\n"
            prompt += "\n"
        
        if suggestion_issues:
            prompt += "### 🟡 建议项（推荐修复）\n"
            for idx, issue in enumerate(suggestion_issues, 1):
                prompt += f"{idx}. [{issue.category}] {issue.description}\n"
                if issue.suggestion:
                    prompt += f"   → 建议：{issue.suggestion}\n"
            prompt += "\n"
        
        if review_result.praise:
            prompt += "### ✅ 值得肯定（保持）\n"
            for p in review_result.praise:
                prompt += f"- {p}\n"
            prompt += "\n"
        
        prompt += "## 重写要求\n"
        prompt += "1. 必须修复所有 🔴 阻塞项\n"
        prompt += "2. 尽量处理 🟡 建议项\n"
        prompt += "3. 保持 ✅ 值得肯定的部分不变\n"
        prompt += "4. 按 Karpathy 铁律：极简、手术刀修改、不加额外功能\n"
        
        return prompt

    def format_for_human(self, review_result: ReviewResult) -> str:
        """格式化审查结果为人类可读报告"""
        lines = []
        lines.append(f"## 审查结果：{'✅ 通过' if review_result.passed else '❌ 否决'}")
        lines.append("")
        
        if review_result.summary:
            lines.append(review_result.summary)
            lines.append("")
        
        if review_result.issues:
            lines.append(f"### 发现 {len(review_result.issues)} 个问题")
            for issue in review_result.issues:
                line_info = f"（第 {issue.line} 行）" if issue.line else ""
                lines.append(f"{issue.severity} [{issue.category}] {line_info} {issue.description}")
                if issue.suggestion:
                    lines.append(f"   → {issue.suggestion}")
            lines.append("")
        
        if review_result.praise:
            lines.append("### 值得肯定")
            for p in review_result.praise:
                lines.append(f"✅ {p}")
            lines.append("")
        
        return "\n".join(lines)


# 快捷函数
def parse_review(raw_text: str) -> ReviewResult:
    """快捷解析审查输出"""
    worker = ReviewerWorker()
    return worker.parse_review_output(raw_text)


def has_veto(review_result: ReviewResult) -> bool:
    """快捷检查是否被否决"""
    return review_result.veto


# 测试
if __name__ == "__main__":
    print("🧪 ReviewerWorker 测试")
    print("="*60)
    
    # 模拟审查输出
    sample_review = """
## 整体评价
代码整体结构清晰，但有 2 个安全问题需要修复。

## 问题列表
🔴 [安全] 第 42 行：SQL 注入风险 — 建议用参数化查询
🟡 [性能] 第 55 行：循环里查数据库 — 建议批量查询
💭 [可读性] 第 10 行：变量名太短 — 建议用描述性命名

## 值得肯定
- 函数拆分合理，职责单一
- 类型注解完整
"""
    
    worker = ReviewerWorker()
    result = worker.parse_review_output(sample_review)
    
    print(f"通过: {result.passed}")
    print(f"否决: {result.veto}")
    print(f"问题数: {len(result.issues)}")
    print(f"值得肯定: {len(result.praise)} 条")
    print()
    print(worker.format_for_human(result))
    
    if result.veto:
        print()
        print("重写提示：")
        print(worker.build_veto_prompt(result, "# 原代码"))
    
    print("\n" + "="*60)
