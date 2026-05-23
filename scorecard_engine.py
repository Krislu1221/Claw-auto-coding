#!/usr/bin/env python3
"""
Risk Scorecard 检测引擎 — v3.7.0

加载 scorecard.yaml，在阶段执行时检测信号是否触发阈值。

功能：
- 按阶段加载 scorecard 条目（含 general 通用条目）
- 阈值表达式求值（支持比较、逻辑运算符、变量替换、布尔字面量）
- 生成 ScorecardReport（包含所有检查结果和摘要统计）
- 冷却窗口（同一类失败 24h 内第 3 次静默，防告警疲劳）
- 阻塞判断（is_blocking）
- 报告格式化（人类可读文本 + JSON 序列化）

Usage:
    from scorecard_engine import ScorecardEngine, CoolDownManager

    engine = ScorecardEngine()
    report = engine.detect("coding", {
        "testing_phase_executed": False,
        "modified_file_count": 7,
        "extra_features_added": 0,
    })
    if engine.is_blocking(report):
        print("🔴 检测到阻塞项")
    print(engine.format_report(report))
"""

import yaml
import re
import ast
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScorecardCheck:
    """单条 Scorecard 检查结果

    Attributes:
        discipline: 纪律名称（如 "不跳过测试"）
        triggered: 是否触发阈值
        signal_value: 当前信号的实际值（类型与信号定义一致）
        threshold: 阈值表达式原文
        action: 触发后的动作（block / warn / log）
        level: 严重级别（🔴 / 🟡 / 💭）
        verdict: 判定结果（"pass" 或详细失败描述）
    """
    discipline: str
    triggered: bool
    signal_value: Any
    threshold: str
    action: str
    level: str
    verdict: str


@dataclass
class ScorecardReport:
    """Scorecard 检测报告

    Attributes:
        phase: 阶段名
        checks: 检查结果列表
        summary: 摘要统计（total, blocked, warned, passed, blocking）
    """
    phase: str
    checks: List[ScorecardCheck] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化 / 日志写入）"""
        return {
            "phase": self.phase,
            "timestamp": datetime.now().isoformat(),
            "checks": [
                {
                    "discipline": c.discipline,
                    "triggered": c.triggered,
                    "signal_value": c.signal_value,
                    "threshold": c.threshold,
                    "action": c.action,
                    "level": c.level,
                    "verdict": c.verdict,
                }
                for c in self.checks
            ],
            "summary": self.summary,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 阈值表达式求值器
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_threshold(threshold: str, signals: Dict[str, Any]) -> bool:
    """求值阈值表达式

    支持的语法：
    - 比较运算符：==  !=  >  <  >=  <=
    - 逻辑运算符：and  or
    - 变量替换：signal_name → signals 字典中的值
    - 布尔字面量：true  false
    - 数字字面量：整数

    实现细节：
    1. 将 true/false 替换为 Python 的 True/False
    2. 将信号变量名替换为 repr(value)（带引号的 Python 字面量）
    3. 用 ast 安全求值（仅支持比较+布尔运算子集）

    Args:
        threshold: 阈值表达式字符串
        signals: 信号值字典 {signal_name: value}

    Returns:
        bool: 表达式求值结果。表达式语法错误或缺信号时返回 False

    Examples:
        >>> evaluate_threshold("testing_phase_executed == false",
        ...                    {"testing_phase_executed": False})
        True
        >>> evaluate_threshold("modified_file_count > 5",
        ...                    {"modified_file_count": 7})
        True
        >>> evaluate_threshold("zoom_out_executed == false and modified_file_count > 3",
        ...                    {"zoom_out_executed": False, "modified_file_count": 5})
        True
    """
    if not threshold or not threshold.strip():
        return False

    expr = threshold

    # 1. 替换布尔字面量（先做，避免与信号名冲突）
    expr = re.sub(r'\btrue\b', 'True', expr)
    expr = re.sub(r'\bfalse\b', 'False', expr)

    # 2. 替换信号变量为实际值（使用 repr 确保类型正确）
    #    按信号名长度降序替换，避免短名先匹配长名的子串
    for name in sorted(signals.keys(), key=len, reverse=True):
        expr = re.sub(r'\b' + re.escape(name) + r'\b', repr(signals[name]), expr)

    # 3. 安全求值 — 用 ast 而非 eval，ClawHub 静态分析零告警
    try:
        result = _safe_bool_eval(expr)
        return result
    except Exception:
        return False


def _safe_bool_eval(expr: str) -> bool:
    """用 ast 安全求值布尔表达式，仅支持比较+布尔运算"""
    import ast

    ALLOWED_NODES = {
        ast.Expression, ast.BoolOp, ast.Compare, ast.Load,
        ast.Constant, ast.UnaryOp, ast.Not,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.And, ast.Or, ast.Name,
    }

    tree = ast.parse(expr.strip(), mode='eval')

    for node in ast.walk(tree):
        if type(node) not in ALLOWED_NODES:
            raise ValueError(f"Unsafe AST node: {type(node).__name__}")

    return bool(_ast_eval_node(tree.body))


def _ast_eval_node(node):
    """递归求值已通过安全检查的 AST 节点"""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _ast_eval_node(node.operand)
    if isinstance(node, ast.BoolOp):
        values = [_ast_eval_node(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.Compare):
        left = _ast_eval_node(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = _ast_eval_node(comp)
            if isinstance(op, ast.Eq):
                result = (left == right)
            elif isinstance(op, ast.NotEq):
                result = (left != right)
            elif isinstance(op, ast.Lt):
                result = (left < right)
            elif isinstance(op, ast.LtE):
                result = (left <= right)
            elif isinstance(op, ast.Gt):
                result = (left > right)
            elif isinstance(op, ast.GtE):
                result = (left >= right)
            else:
                raise ValueError(f"Unknown comparison: {type(op).__name__}")
            if not result:
                return False
            left = right  # 链式比较 a == b == c
        return True
    raise ValueError(f"Unsupported node: {type(node).__name__}")


# ═══════════════════════════════════════════════════════════════════════════
# 冷却窗口管理器
# ═══════════════════════════════════════════════════════════════════════════

class CoolDownManager:
    """反馈冷却窗口 — 防告警疲劳

    同一类失败在 24 小时内触发第 3 次时静默，避免重复告警轰炸。

    Usage:
        cm = CoolDownManager()

        # 检查是否该静默
        if cm.should_silence("skip_testing"):
            print("已静默 — 第 3 次同类型失败，24h 内不再告警")
        else:
            cm.record_failure("skip_testing")
    """

    def __init__(self):
        self.failure_history: Dict[str, list] = {}
        """失败类型 → 时间戳列表（按时间升序）"""

    def record_failure(self, failure_type: str) -> None:
        """记录一次失败

        Args:
            failure_type: 失败类型标识（如 discipline 名称）
        """
        now = datetime.now()
        if failure_type not in self.failure_history:
            self.failure_history[failure_type] = []
        self.failure_history[failure_type].append(now)
        self._prune(failure_type)

    def should_silence(self, failure_type: str) -> bool:
        """判断是否应该静默告警

        规则：同一类失败 24h 内已有 ≥2 次记录 → 静默（第 3 次及以后不告警）

        Args:
            failure_type: 失败类型标识

        Returns:
            bool: True 表示应静默
        """
        if failure_type not in self.failure_history:
            return False

        self._prune(failure_type)
        # ≥2 次意味着下次是第 3 次 → 静默
        return len(self.failure_history[failure_type]) >= 2

    def get_count(self, failure_type: str) -> int:
        """获取 24 小时内的失败次数

        Args:
            failure_type: 失败类型标识

        Returns:
            int: 24h 内失败次数
        """
        if failure_type not in self.failure_history:
            return 0
        self._prune(failure_type)
        return len(self.failure_history[failure_type])

    def reset(self, failure_type: str = None) -> None:
        """重置冷却计数

        Args:
            failure_type: 指定类型重置，None 则全部重置
        """
        if failure_type:
            self.failure_history.pop(failure_type, None)
        else:
            self.failure_history.clear()

    def _prune(self, failure_type: str) -> None:
        """清理 24 小时外的过期记录"""
        if failure_type not in self.failure_history:
            return
        cutoff = datetime.now() - timedelta(hours=24)
        self.failure_history[failure_type] = [
            ts for ts in self.failure_history[failure_type]
            if ts > cutoff
        ]


# ═══════════════════════════════════════════════════════════════════════════
# Scorecard 引擎
# ═══════════════════════════════════════════════════════════════════════════

class ScorecardEngine:
    """Risk Scorecard 检测引擎

    加载 scorecard.yaml，在阶段执行前/中/后检测信号是否触发阈值。

    执行流程：
    1. Pre-Mortem（阶段前）：Agent 对照 rationalizations 自检
    2. In-Flight（阶段中）：关键操作后检测 signal 对比 threshold
    3. Post-Mortem（阶段后）：聚合结果 → 生成 Report → 写入日志

    Usage:
        engine = ScorecardEngine()
        checks = engine.get_checks("coding")
        report = engine.detect("coding", signals_dict)
        if engine.is_blocking(report):
            print("⛔ 阶段不能继续")
        else:
            print(engine.format_report(report))
    """

    # 阶段名 → YAML section key 映射
    PHASE_MAP = {
        "design":        "general",      # 设计阶段只有 general
        "decomposition": "general",      # 分解阶段只有 general
        "coding":        "coding",
        "testing":       "testing",
        "reflection":    "review",       # reflection → review
        "review":        "review",
        "optimization":  "general",
        "verification":  "general",
    }

    def __init__(self, config_path: str = None, cooldown_manager: CoolDownManager = None):
        """初始化引擎，加载 scorecard.yaml

        Args:
            config_path: scorecard.yaml 路径，默认使用内置配置
            cooldown_manager: 冷却窗口管理器（可选，不传则自动创建）
        """
        if config_path is None:
            config_path = Path(__file__).parent / "configs" / "scorecard.yaml"

        self.config_path = Path(config_path)
        self.cooldown = cooldown_manager or CoolDownManager()

        if not self.config_path.exists():
            raise FileNotFoundError(f"scorecard.yaml 不存在: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.version = self.config.get("version", "unknown")
        self.meta = self.config.get("meta", {})

    # ── 阶段条目获取 ─────────────────────────────────────────────────────

    def get_checks(self, phase: str) -> list:
        """获取某阶段的 scorecard 条目列表

        加载规则：
        - coding     → coding section + general section
        - testing    → testing section + general section
        - reflection → review section + general section
        - 其他阶段   → general section only

        Args:
            phase: 阶段名（design / decomposition / coding / testing /
                   reflection / review / optimization / verification）

        Returns:
            list[dict]: Scorecard 条目列表，每个条目含 discipline / signal /
                        threshold / action / level 等字段
        """
        checks = []

        # 加载阶段特定条目
        yaml_key = self.PHASE_MAP.get(phase, "general")
        if yaml_key in self.config and yaml_key != "general":
            checks.extend(self.config.get(yaml_key, []))

        # 始终加载 general 条目（所有阶段通用纪律）
        checks.extend(self.config.get("general", []))

        return checks

    # ── 信号检测 ─────────────────────────────────────────────────────────

    def detect(self, phase: str, signals: Dict[str, Any]) -> ScorecardReport:
        """检测信号是否触发阈值 — 核心方法

        对每个 scorecard 条目：
        1. 从 signals 字典获取当前信号值
        2. 用 evaluate_threshold() 求值阈值表达式
        3. 生成 ScorecardCheck（含冷却窗口检查）

        Args:
            phase: 阶段名
            signals: 信号值字典 {signal_name: value}
                     支持的信号名见 scorecard.yaml 中各 entry.signal 字段

        Returns:
            ScorecardReport: 含所有检查结果和摘要统计

        Example:
            >>> engine = ScorecardEngine()
            >>> signals = {
            ...     "testing_phase_executed": False,
            ...     "modified_file_count": 7,
            ...     "extra_features_added": 0,
            ...     "new_code_without_test": 50,
            ...     "abstraction_layers_added": 0,
            ...     "tests_passed_after_change": True,
            ...     "feedback_loop_established": True,
            ...     "debug_attempts": 0,
            ... }
            >>> report = engine.detect("coding", signals)
            >>> report.summary["blocking"]
            True  # modified_file_count=7 > 5 触发阻塞
        """
        checks_data = self.get_checks(phase)
        report = ScorecardReport(phase=phase)

        for entry in checks_data:
            discipline = entry.get("discipline", "未命名纪律")
            signal_name = entry.get("signal", "")
            threshold_expr = entry.get("threshold", "")
            action = entry.get("action", "log")
            level = entry.get("level", "💭")

            # 获取信号值（缺失时默认 None，表达式求值会处理）
            signal_value = signals.get(signal_name)

            # 求值阈值
            triggered = evaluate_threshold(threshold_expr, signals)

            # 生成判定结果
            if triggered:
                # 冷却窗口：同一类失败 24h 内第 3 次 → 静默
                if action == "block" and self.cooldown.should_silence(discipline):
                    verdict = (
                        f"💭 已静默（24h 内第 "
                        f"{self.cooldown.get_count(discipline) + 1} 次触发）"
                    )
                    # 静默时不记录触发 → 避免进一步疲劳
                    triggered = False
                else:
                    verdict = _build_trigger_verdict(
                        level, action, discipline, signal_value, threshold_expr
                    )
                    # 记录失败（用于冷却窗口累计）
                    if action == "block":
                        self.cooldown.record_failure(discipline)
            else:
                verdict = "pass"

            check = ScorecardCheck(
                discipline=discipline,
                triggered=triggered,
                signal_value=signal_value,
                threshold=threshold_expr,
                action=action,
                level=level,
                verdict=verdict,
            )
            report.checks.append(check)

        # 生成摘要统计
        total = len(report.checks)
        blocked = sum(1 for c in report.checks if c.triggered and c.action == "block")
        warned = sum(1 for c in report.checks if c.triggered and c.action == "warn")
        logged = sum(1 for c in report.checks if c.triggered and c.action == "log")
        passed = total - blocked - warned - logged
        blocking = blocked > 0

        report.summary = {
            "total": total,
            "blocked": blocked,
            "warned": warned,
            "logged": logged,
            "passed": passed,
            "blocking": blocking,
        }

        return report

    # ── 阻塞判断 ─────────────────────────────────────────────────────────

    def is_blocking(self, report: ScorecardReport) -> bool:
        """是否有阻塞级触发

        任何 🔴 block 被触发 → 阶段不能继续，必须通知主会话。

        Args:
            report: ScorecardReport

        Returns:
            bool: True 表示有阻塞，阶段应暂停
        """
        return report.summary.get("blocking", False)

    # ── 报告格式化 ───────────────────────────────────────────────────────

    def format_report(self, report: ScorecardReport) -> str:
        """格式化报告为人类可读文本

        输出包含：
        - 标题行（阶段名）
        - 逐条检查结果（icon + action + discipline + signal + verdict）
        - 摘要统计

        Args:
            report: ScorecardReport

        Returns:
            str: 格式化文本
        """
        lines = []
        phase_name = report.phase.upper()

        # 标题
        lines.append("╔══════════════════════════════════════════════╗")
        lines.append(f"║  📊 Risk Scorecard Report — {phase_name:12s}          ║")
        lines.append("╚══════════════════════════════════════════════╝")
        lines.append("")

        # 逐条检查
        for check in report.checks:
            icon = check.level if check.triggered else "✅"
            label = check.action.upper()
            lines.append(f"  {icon} [{label:5s}] {check.discipline}")
            lines.append(f"     信号: {_fmt_signal(check.signal_value)}  "
                         f"| 阈值: {check.threshold}")
            lines.append(f"     判定: {check.verdict}")
            lines.append("")

        # 摘要
        s = report.summary
        lines.append("  " + "─" * 42)
        parts = [f"📋 共 {s['total']} 条"]
        if s["blocked"]:
            parts.append(f"🔴 阻塞 {s['blocked']}")
        if s["warned"]:
            parts.append(f"🟡 警告 {s['warned']}")
        if s["logged"]:
            parts.append(f"💭 记录 {s['logged']}")
        parts.append(f"✅ 通过 {s['passed']}")
        lines.append("  " + " | ".join(parts))
        lines.append(f"  ⛔ 阻塞状态: {'是 ⛔' if s['blocking'] else '否 ✅'}")
        lines.append("  " + "─" * 42)

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════

def _build_trigger_verdict(
    level: str, action: str, discipline: str,
    signal_value: Any, threshold: str
) -> str:
    """构建触发的详细判定描述"""
    action_text = {
        "block": "触发阻塞",
        "warn":  "触发警告",
        "log":   "触发记录",
    }
    desc = action_text.get(action, "触发")
    return (
        f"{level} {desc}: {discipline}"
        f"（信号值={_fmt_signal(signal_value)}，阈值={threshold}）"
    )


def _fmt_signal(value: Any) -> str:
    """格式化信号值为可读字符串"""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


# ═══════════════════════════════════════════════════════════════════════════
# 便捷工厂函数
# ═══════════════════════════════════════════════════════════════════════════

def create_engine(config_path: str = None) -> ScorecardEngine:
    """工厂函数：创建 ScorecardEngine 实例

    Args:
        config_path: scorecard.yaml 路径，默认使用内置配置

    Returns:
        ScorecardEngine: 已初始化并加载配置的引擎实例
    """
    return ScorecardEngine(config_path=config_path)


# ═══════════════════════════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    failed = 0

    def check(name, actual, expected):
        global failed
        ok = actual == expected
        status = "✅" if ok else "❌"
        if not ok:
            failed += 1
            print(f"  {status} {name}: got {actual!r}, expected {expected!r}")
        else:
            print(f"  {status} {name}")

    print("=" * 60)
    print("🧪 Scorecard Engine 自测")
    print("=" * 60)

    # ── 1. 引擎初始化 ──────────────────────────────────────────────────
    print("\n1️⃣  引擎初始化")
    engine = ScorecardEngine()
    print(f"   ✅ 版本: {engine.version}")
    print(f"   ✅ 配置路径: {engine.config_path}")

    # ── 2. get_checks ───────────────────────────────────────────────────
    print("\n2️⃣  get_checks() 阶段条目获取")

    coding = engine.get_checks("coding")
    check("coding + general 条目数", len(coding), 7)  # 5 coding + 2 general

    testing = engine.get_checks("testing")
    check("testing + general 条目数", len(testing), 4)  # 2 testing + 2 general

    reflection = engine.get_checks("reflection")
    check("reflection → review + general", len(reflection), 5)  # 3 review + 2 general

    design = engine.get_checks("design")
    check("design (general only)", len(design), 2)  # 2 general

    for c in coding:
        print(f"   - {c['level']} {c['discipline']} → {c['signal']}")

    # ── 3. detect() + 阈值求值 ──────────────────────────────────────────
    print("\n3️⃣  detect() 信号检测")

    signals = {
        "testing_phase_executed": False,
        "modified_file_count": 7,
        "extra_features_added": 0,
        "new_code_without_test": 50,
        "abstraction_layers_added": 0,
        "tests_passed_after_change": True,
        "feedback_loop_established": True,
        "debug_attempts": 0,
    }

    report = engine.detect("coding", signals)
    check("coding 检测条目数", len(report.checks), 7)
    check("summary.total", report.summary["total"], 7)
    check("summary.blocking (modified_file_count=7 > 5)", report.summary["blocking"], True)
    check("summary.blocked (2 项: 不跳过测试 + 手术刀式修改)", report.summary["blocked"], 2)

    # 验证具体检查项
    testing_check = [c for c in report.checks if c.discipline == "不跳过测试"][0]
    check("不跳过测试 triggered", testing_check.triggered, True)
    check("不跳过测试 action", testing_check.action, "block")

    surgery_check = [c for c in report.checks if c.discipline == "手术刀式修改"][0]
    check("手术刀式修改 triggered (signal=7 > 5)", surgery_check.triggered, True)

    # ── 4. is_blocking ─────────────────────────────────────────────────
    print("\n4️⃣  is_blocking()")

    check("阻塞判断", engine.is_blocking(report), True)

    # 全通过的 signals
    clean_signals = {
        "testing_phase_executed": True,
        "modified_file_count": 2,
        "extra_features_added": 0,
        "new_code_without_test": 50,
        "abstraction_layers_added": 0,
        "tests_passed_after_change": True,
        "feedback_loop_established": True,
        "debug_attempts": 0,
    }
    clean_report = engine.detect("coding", clean_signals)
    check("全通过时 blocking=False", clean_report.summary["blocking"], False)

    # ── 5. format_report ────────────────────────────────────────────────
    print("\n5️⃣  format_report()")
    formatted = engine.format_report(report)
    print(formatted)

    # ── 6. 阈值求值器 ──────────────────────────────────────────────────
    print("\n6️⃣  evaluate_threshold() 表达式求值")

    eval_tests = [
        ("== false",     "testing_phase_executed == false",
         {"testing_phase_executed": False}, True),
        ("> 5 触发",     "modified_file_count > 5",
         {"modified_file_count": 7}, True),
        ("> 5 不触发",   "modified_file_count > 5",
         {"modified_file_count": 3}, False),
        ("> 0 false",    "extra_features_added > 0",
         {"extra_features_added": 0}, False),
        ("> 1 触发",     "abstraction_layers_added > 1",
         {"abstraction_layers_added": 2}, True),
        ("and 复合 true","zoom_out_executed == false and modified_file_count > 3",
         {"zoom_out_executed": False, "modified_file_count": 5}, True),
        ("and 复合 false","feedback_loop_established == false and debug_attempts > 0",
         {"feedback_loop_established": True, "debug_attempts": 2}, False),
        ("== false 不触","tests_passed_after_change == false",
         {"tests_passed_after_change": True}, False),
        ("== true 触发",  "test_touches_internal_api == true",
         {"test_touches_internal_api": True}, True),
        (">= 200",        "new_code_without_test >= 200",
         {"new_code_without_test": 200}, True),
        (">= 200 false",  "new_code_without_test >= 200",
         {"new_code_without_test": 199}, False),
        ("空字符串",      "",
         {}, False),
    ]

    for name, expr, sigs, expected in eval_tests:
        result = evaluate_threshold(expr, sigs)
        check(f"阈值: {name} ({expr})", result, expected)

    # ── 7. 冷却窗口 ────────────────────────────────────────────────────
    print("\n7️⃣  CoolDownManager 冷却窗口")
    cm = CoolDownManager()

    check("初始 count=0", cm.get_count("t1"), 0)
    check("初始 不静默", cm.should_silence("t1"), False)

    cm.record_failure("t1")
    check("1 次后 count=1", cm.get_count("t1"), 1)
    check("1 次后 不静默", cm.should_silence("t1"), False)

    cm.record_failure("t1")
    check("2 次后 count=2", cm.get_count("t1"), 2)
    check("2 次后 静默（第 3 次静默）", cm.should_silence("t1"), True)

    # 不同失败类型不互相影响
    check("不同类型 count=0", cm.get_count("t2"), 0)
    check("不同类型 不静默", cm.should_silence("t2"), False)

    cm.record_failure("t2")
    check("t2 1 次后 不静默", cm.should_silence("t2"), False)

    # reset
    cm.reset("t1")
    check("reset t1 后 count=0", cm.get_count("t1"), 0)
    check("reset t1 后 不静默", cm.should_silence("t1"), False)

    # ── 8. ScorecardReport.to_dict() ────────────────────────────────────
    print("\n8️⃣  ScorecardReport.to_dict()")
    d = report.to_dict()
    check("to_dict phase", d["phase"], "coding")
    check("to_dict checks 数", len(d["checks"]), 7)
    check("to_dict summary", d["summary"]["blocking"], True)

    # ── 9. 审查阶段 (reflection → review) ──────────────────────────────
    print("\n9️⃣  审查阶段检测")
    review_signals = {
        "zoom_out_executed": False,
        "modified_file_count": 5,
        "security_checks_passed": True,
        "over_critique_detected": False,
        "tests_passed_after_change": True,
        "feedback_loop_established": True,
        "debug_attempts": 0,
    }
    review_report = engine.detect("reflection", review_signals)
    check("reflection 检测条目数", len(review_report.checks), 5)
    # zoom_out_executed==false and modified_file_count>3 → 触发警告
    zoom_check = [c for c in review_report.checks if c.discipline == "审查前先 zoom-out"][0]
    check("审查前先 zoom-out triggered", zoom_check.triggered, True)
    check("审查前先 zoom-out action=warn", zoom_check.action, "warn")

    # ── 结果汇总 ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failed == 0:
        print("🎉 全部通过！")
    else:
        print(f"❌ {failed} 项失败")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
