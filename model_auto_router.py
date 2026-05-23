#!/usr/bin/env python3
"""
Model Auto Router — v3.7.0

Per-Turn 自动模型路由：参考 DeepSeek TUI 的 Auto Mode 设计。
Pro 做"大脑"（推理、设计、审查），Flash 做"手"（执行、写入、验证）。

核心原则：
- Pro 定义"做什么"和"对不对"
- Flash 执行"怎么做"
- 修改现有代码（非独立创建）→ 升回 Pro

路由决策三要素：
1. 阶段（phase）— 基本路由表
2. 任务类型（category）— 例外覆盖（如集成修改）
3. 上下文大小（token estimate）— Pro 有 1M 窗口优势

使用：
    router = ModelAutoRouter()
    model, thinking = router.route(phase="coding", category="code-generation")
    # → ("deepseek-v4-flash", "off")
"""

from typing import Tuple, Optional


# ── 主路由表 ─────────────────────────────────────────

# 阶段 → (模型, thinking)
PHASE_ROUTING = {
    # Pro 层：需要深度推理
    "design":          ("deepseek/deepseek-v4-pro", "high"),
    "decomposition":   ("deepseek/deepseek-v4-pro", "off"),
    "reflection":      ("deepseek/deepseek-v4-pro", "high"),  # 审查
    "optimize":        ("deepseek/deepseek-v4-pro", "high"),  # 重构

    # Flash 层：执行/写入/验证
    "coding":          ("deepseek/deepseek-v4-flash", "off"),
    "testing":         ("deepseek/deepseek-v4-flash", "off"),
    "verification":    ("deepseek/deepseek-v4-flash", "off"),
    "diagnose":        ("deepseek/deepseek-v4-flash", "off"),  # 调试也是执行

    # 可选阶段
    "architecture_check": ("deepseek/deepseek-v4-pro", "off"),
}


# 任务类型覆盖：某些类型即使阶段在 Flash 层，也要升回 Pro
CATEGORY_UPGRADE = {
    # 修改现有代码（非独立创建）→ Pro
    "integration": ("deepseek/deepseek-v4-pro", "off"),
    # 深度分析 → Pro
    "text-critique": ("deepseek/deepseek-v4-pro", "high"),
    "text-analysis": ("deepseek/deepseek-v4-pro", "off"),
}


# 上下文阈值：token 超限时 Pro 的 1M 窗口优势
CONTEXT_THRESHOLD_PRO = 50_000  # 超过 50k token 建议用 Pro（更大的上下文窗口）


# ── 主类 ─────────────────────────────────────────────

class ModelAutoRouter:
    """
    自动模型路由决策引擎。

    决策顺序：
    1. 查 PHASE_ROUTING → 默认模型
    2. 查 CATEGORY_UPGRADE → 是否需要升回 Pro
    3. 查上下文阈值 → 大上下文强制 Pro
    4. 返回 (model, thinking_level)
    """

    def __init__(self, default_model: str = "deepseek/deepseek-v4-pro"):
        self.default_model = default_model
        self.default_thinking = "off"

    def route(
        self,
        phase: str,
        category: Optional[str] = None,
        context_tokens: int = 0,
        force_pro: bool = False,
    ) -> Tuple[str, str]:
        """
        路由决策。

        Args:
            phase: 阶段名（design/coding/testing/...）
            category: 任务类型（code-generation/integration/...）
            context_tokens: 预估上下文 token 数
            force_pro: 强制使用 Pro（用户显式指定时）

        Returns:
            (model_string, thinking_level)
            model_string: 如 "deepseek/deepseek-v4-pro"
            thinking_level: "off" | "high"
        """
        if force_pro:
            return (self.default_model, "off")

        # Step 1: 查阶段路由
        model, thinking = PHASE_ROUTING.get(
            phase,
            (self.default_model, self.default_thinking)
        )

        # Step 2: 任务类型覆盖
        if category and category in CATEGORY_UPGRADE:
            model, thinking = CATEGORY_UPGRADE[category]

        # Step 3: 大上下文 → Pro
        if context_tokens > CONTEXT_THRESHOLD_PRO and "pro" not in model.lower():
            model = self.default_model

        return (model, thinking)

    def explain(self, phase: str, category: Optional[str] = None,
                context_tokens: int = 0) -> str:
        """人类可读的路由解释"""
        model, thinking = self.route(phase, category, context_tokens)
        tier = "Pro（推理层）" if "pro" in model.lower() else "Flash（执行层）"
        lines = [
            f"阶段: {phase}",
            f"类型: {category or '未指定'}",
            f"上下文: {context_tokens} tokens",
            f"→ 模型: {model} ({tier})",
            f"→ Thinking: {thinking}",
        ]
        if category and category in CATEGORY_UPGRADE:
            lines.append("   ⚡ 分类覆盖：此类型需要 Pro 深度推理")
        if context_tokens > CONTEXT_THRESHOLD_PRO:
            lines.append("   ⚡ 上下文覆盖：大上下文建议 Pro（1M 窗口优势）")
        return "\n".join(lines)

    def iter_phases(self):
        """遍历所有已知阶段的路由配置"""
        return PHASE_ROUTING.items()


# ── 便捷函数 ─────────────────────────────────────────

_router = None

def auto_route(phase: str, category: Optional[str] = None,
               context_tokens: int = 0) -> Tuple[str, str]:
    """全局便捷函数"""
    global _router
    if _router is None:
        _router = ModelAutoRouter()
    return _router.route(phase, category, context_tokens)


# ── 自测 ─────────────────────────────────────────────

if __name__ == "__main__":
    router = ModelAutoRouter()

    tests = [
        # (phase, category, context, expected_model_tier, expected_thinking)
        ("design",          "text-analysis",   0,     "pro",   "off"),   # 分类覆盖 thinking
        ("coding",          "code-generation", 0,     "flash", "off"),   # 独立创建
        ("coding",          "integration",     0,     "pro",   "off"),   # 修改现有
        ("testing",         None,              0,     "flash", "off"),
        ("reflection",      "review",          0,     "pro",   "high"),
        ("verification",    None,              0,     "flash", "off"),
        ("coding",          "code-generation", 60000, "pro",   "off"),   # 大上下文
        ("reflection",      "review",          0,     "pro",   "high"),
        # force_pro
        ("coding",          "code-generation", 0,     "pro",   "off"),   # 强制
    ]

    force_pro_flags = [False, False, False, False, False, False, False, False, True]

    all_pass = True
    for i, ((phase, cat, ctx, exp_tier, exp_thinking), force) in enumerate(
        zip(tests, force_pro_flags), 1
    ):
        model, thinking = router.route(phase, cat, ctx, force_pro=force)
        actual_tier = "pro" if "pro" in model.lower() else "flash"
        tier_ok = actual_tier == exp_tier
        think_ok = thinking == exp_thinking
        status = "✅" if (tier_ok and think_ok) else "❌"
        if not (tier_ok and think_ok):
            all_pass = False
            print(f"{status} Test {i}: {phase}/{cat} → {model}/{thinking} "
                  f"(expected {exp_tier}/{exp_thinking})")
        else:
            print(f"{status} Test {i}: {phase}/{cat} → {model}/{thinking}")

    print()

    # 人类可读解释
    print(router.explain("coding", "integration", 0))
    print()
    print(router.explain("coding", "code-generation", 0))
    print()
    print(router.explain("coding", "code-generation", 60000))

    print()
    if all_pass:
        print("✅ ModelAutoRouter 全部测试通过")
    else:
        print("❌ 有测试失败，请检查路由规则")
