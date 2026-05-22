#!/usr/bin/env python3
"""
Task Profiler — v3.7-discipline

项目级任务画像系统。持续积累每次子代理任务的实际耗时、token 数据，
按任务类型/模型/阶段动态校准超时窗口 + 中断风险预测。

功能：
- 记录每次子代理任务的历史数据（category, model, estimated, actual, status）
- 按 category 计算 adjust 系数（实际/预估 的滑动平均）
- 按 phase 计算中断风险指数
- 按 model 计算基准耗时
- 下次 spawn 时提供校准后的超时窗口

使用：
    profiler = TaskProfiler(project_dir)
    profiler.record(task_id, category, model, estimated, actual, status)
    window = profiler.calibrate_window(category, "deepseek-v4-pro", base_minutes=5)

数据文件：.auto-coding/.profile.json
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict


# ── 数据模型 ────────────────────────────────────────────

@dataclass
class TaskRecord:
    """单次子代理任务的历史记录"""
    task_id: str
    category: str          # code-generation | yaml-config | review | text-analysis | multi-file | integration
    model: str
    phase: str             # design | decomposition | coding | testing | reflection | optimize | verification
    estimated_minutes: float
    actual_minutes: float
    token_count: int
    file_count: int         # 产出文件数
    status: str            # completed | timeout | failed | retried
    recorded_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CategoryProfile:
    """按任务类型的画像统计"""
    count: int = 0
    avg_actual: float = 0.0
    avg_estimated: float = 0.0
    adjust_factor: float = 1.0   # 实际/预估 — 下次预估值乘这个系数
    timeout_rate: float = 0.0
    fail_rate: float = 0.0

    def update(self, record: TaskRecord):
        self.count += 1
        n = self.count
        # 增量更新滑动平均
        self.avg_actual = self.avg_actual * (n - 1) / n + record.actual_minutes / n
        self.avg_estimated = self.avg_estimated * (n - 1) / n + record.estimated_minutes / n
        if self.avg_estimated > 0:
            self.adjust_factor = self.avg_actual / self.avg_estimated
        self.timeout_rate = (self.timeout_rate * (n - 1) + (1 if record.status == "timeout" else 0)) / n
        self.fail_rate = (self.fail_rate * (n - 1) + (1 if record.status in ("failed", "timeout") else 0)) / n


@dataclass
class PhaseRisk:
    """按阶段的中断风险画像"""
    phase: str
    total: int = 0
    failed: int = 0
    timeouts: int = 0
    avg_duration: float = 0.0

    @property
    def risk_index(self) -> float:
        """中断风险指数 0-1"""
        if self.total == 0:
            return 0.0
        return (self.failed + self.timeouts * 1.5) / self.total

    @property
    def risk_level(self) -> str:
        if self.risk_index >= 0.4:
            return "high"
        elif self.risk_index >= 0.15:
            return "medium"
        return "low"


# ── 主类 ────────────────────────────────────────────────

class TaskProfiler:
    """项目级任务画像系统"""

    # 任务类型 → 预估公式系数（首次无历史时用）
    DEFAULT_ESTIMATES = {
        "code-generation":   {"base": 2, "per_file": 1.5, "per_token_k": 0.02},
        "multi-file":        {"base": 3, "per_file": 1.5, "per_token_k": 0.02},
        "yaml-config":       {"base": 1, "per_file": 1.0, "per_token_k": 0.01},
        "review":            {"base": 3, "per_file": 2.0, "per_token_k": 0.03},
        "text-analysis":     {"base": 2, "per_file": 1.0, "per_token_k": 0.04},  # RoundTable
        "text-critique":     {"base": 3, "per_file": 1.5, "per_token_k": 0.05},  # RoundTable R3
        "integration":       {"base": 4, "per_file": 3.0, "per_token_k": 0.03},
    }

    # 模型速度系数（deepseek-v4-pro = 1.0 基准）
    MODEL_SPEED_FACTORS = {
        "deepseek-v4-pro": 1.0,
        "deepseek-deepseek-v4-pro": 1.0,
        "mimo-v2.5-pro": 0.6,
        "doubao-seed-2.0-pro": 0.8,
        "doubao-seed-2.0-lite": 0.4,
    }

    def __init__(self, project_dir=None):
        if project_dir is None:
            project_dir = Path.cwd()
        self.project_dir = Path(project_dir)
        self.profile_path = self.project_dir / ".auto-coding" / ".profile.json"
        self.data = self._load()

    # ── IO ────────────────────────────────────────

    def _load(self) -> dict:
        if self.profile_path.exists():
            try:
                with open(self.profile_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._empty_profile()

    def _save(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profile_path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)

    def _empty_profile(self) -> dict:
        return {
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [],
            "category_profiles": {},
            "phase_risks": {},
            "model_stats": {},
        }

    # ── 核心 API ──────────────────────────────────

    def record(
        self,
        task_id: str,
        category: str,
        model: str,
        phase: str,
        estimated_minutes: float,
        actual_minutes: float,
        token_count: int = 0,
        file_count: int = 0,
        status: str = "completed",
    ):
        """记录一次子代理任务的执行数据"""
        record = TaskRecord(
            task_id=task_id,
            category=category,
            model=model,
            phase=phase,
            estimated_minutes=estimated_minutes,
            actual_minutes=actual_minutes,
            token_count=token_count,
            file_count=file_count,
            status=status,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        self.data["tasks"].append(record.to_dict())

        # 更新分类画像
        if category not in self.data["category_profiles"]:
            self.data["category_profiles"][category] = {}
        cat_profile = CategoryProfile(**self.data["category_profiles"].get(category, {}))
        cat_profile.update(record)
        self.data["category_profiles"][category] = {
            "count": cat_profile.count,
            "avg_actual": round(cat_profile.avg_actual, 2),
            "avg_estimated": round(cat_profile.avg_estimated, 2),
            "adjust_factor": round(cat_profile.adjust_factor, 3),
            "timeout_rate": round(cat_profile.timeout_rate, 3),
            "fail_rate": round(cat_profile.fail_rate, 3),
        }

        # 更新阶段风险
        if phase not in self.data["phase_risks"]:
            self.data["phase_risks"][phase] = {"phase": phase, "total": 0, "failed": 0, "timeouts": 0, "avg_duration": 0.0}
        pr = self.data["phase_risks"][phase]
        pr["total"] += 1
        if status == "failed":
            pr["failed"] += 1
        if status == "timeout":
            pr["timeouts"] += 1
            pr["failed"] += 1
        pr["avg_duration"] = round(pr["avg_duration"] * (pr["total"] - 1) / pr["total"] + actual_minutes / pr["total"], 2)

        # 更新模型统计
        if model not in self.data["model_stats"]:
            self.data["model_stats"][model] = {"count": 0, "avg_actual": 0.0, "timeout_rate": 0.0}
        ms = self.data["model_stats"][model]
        n = ms["count"] + 1
        ms["avg_actual"] = round(ms["avg_actual"] * (n - 1) / n + actual_minutes / n, 2)
        ms["timeout_rate"] = round(ms["timeout_rate"] * (n - 1) / n + (1 if status == "timeout" else 0) / n, 3)
        ms["count"] = n

        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def estimate(self, category: str, file_count: int = 0, estimated_tokens: int = 0) -> float:
        """
        静态预估任务耗时（首次无历史时用）。
        
        Args:
            category: 任务类型
            file_count: 预期产出文件数
            estimated_tokens: 预估 token 数
        Returns:
            预估分钟数
        """
        coeffs = self.DEFAULT_ESTIMATES.get(category, self.DEFAULT_ESTIMATES["code-generation"])
        base = coeffs["base"]
        file_time = coeffs["per_file"] * file_count
        token_time = coeffs["per_token_k"] * (estimated_tokens / 1000)
        return round(base + file_time + token_time, 1)

    def calibrate_window(
        self,
        category: str,
        model: str = "deepseek-v4-pro",
        base_minutes: float = 5.0,
        risk_buffer: float = 1.5,
    ) -> dict:
        """
        校准超时窗口：静态预估 × 分类调整系数 × 模型速度系数 × 风险缓冲。
        
        Args:
            category: 任务类型
            model: 使用的模型
            base_minutes: 静态预估的分钟数
            risk_buffer: 风险缓冲倍率（默认 1.5）
        Returns:
            {
                "window_minutes": float,      # 建议超时窗口
                "check_minutes": float,       # 建议首次检查时间
                "adjust_factor": float,       # 分类调整系数
                "model_factor": float,        # 模型速度系数
                "risk_level": str,            # high / medium / low
                "confidence": str,            # high / medium / low
            }
        """
        # 分类调整系数
        cat_data = self.data["category_profiles"].get(category, {})
        adjust = cat_data.get("adjust_factor", 1.0)
        if adjust <= 0:
            adjust = 1.0

        # 模型速度系数
        model_factor = self.MODEL_SPEED_FACTORS.get(model, 1.0)

        # 任务数太少 → 降低置信度
        task_count = cat_data.get("count", 0)
        if task_count == 0:
            confidence = "low"
        elif task_count < 3:
            confidence = "medium"
        else:
            confidence = "high"

        # 校准
        calibrated = base_minutes * adjust * model_factor
        window = calibrated * risk_buffer
        check_minutes = calibrated * 0.7  # 70% 时间点先检查一次

        # 风险等级（从 phase_risks 取最高的）
        risk_level = "low"
        max_risk = 0.0
        for pr in self.data.get("phase_risks", {}).values():
            if pr.get("total", 0) > 0:
                r = PhaseRisk(**pr).risk_index
                if r > max_risk:
                    max_risk = r
        if max_risk >= 0.4:
            risk_level = "high"
        elif max_risk >= 0.15:
            risk_level = "medium"

        return {
            "window_minutes": round(window, 1),
            "check_minutes": round(check_minutes, 1),
            "adjust_factor": round(adjust, 3),
            "model_factor": round(model_factor, 2),
            "risk_level": risk_level,
            "confidence": confidence,
            "history_count": task_count,
        }

    def get_phase_risk(self, phase: str) -> PhaseRisk:
        """获取特定阶段的中断风险"""
        pr_data = self.data.get("phase_risks", {}).get(phase, {})
        return PhaseRisk(**pr_data) if pr_data else PhaseRisk(phase=phase)

    def get_category_profile(self, category: str) -> Optional[dict]:
        """获取特定分类的画像"""
        return self.data.get("category_profiles", {}).get(category)

    def summary(self) -> str:
        """人类可读的画像摘要"""
        lines = ["## 任务画像摘要", ""]
        tasks = self.data.get("tasks", [])
        lines.append(f"总任务数: {len(tasks)}")

        # 分类统计
        lines.append("\n### 按任务类型")
        for cat, profile in self.data.get("category_profiles", {}).items():
            c = profile.get("count", 0)
            adj = profile.get("adjust_factor", 1.0)
            fail = profile.get("fail_rate", 0)
            lines.append(f"- **{cat}**: {c} 次, adjust={adj}, 失败率={fail:.0%}")

        # 阶段风险
        lines.append("\n### 阶段中断风险")
        for phase, pr in sorted(self.data.get("phase_risks", {}).items(),
                                key=lambda x: PhaseRisk(**x[1]).risk_index, reverse=True):
            r = PhaseRisk(**pr)
            lines.append(f"- **{phase}**: {pr['total']} 次, 风险={r.risk_level} ({r.risk_index:.0%}), 平均{r.avg_duration:.0f}分")

        # 模型统计
        if self.data.get("model_stats"):
            lines.append("\n### 模型耗时")
            for model, ms in self.data["model_stats"].items():
                lines.append(f"- **{model}**: {ms['count']} 次, 平均 {ms['avg_actual']:.0f}分")

        return "\n".join(lines)


# ── 便捷函数 ────────────────────────────────────────────

def classify_task(prompt_text: str, file_count: int = 0) -> str:
    """
    从 prompt 内容推断任务类型。
    
    启发式规则：
    - "YAML"/"yaml"/"config" → yaml-config
    - "审查"/"review"/"critique" → review
    - "分析"/"analyze" + 低文件数 → text-analysis
    - "批判"/"深度批判" → text-critique
    - 多文件(>3) + 代码 → multi-file
    - 默认 → code-generation
    """
    prompt_lower = prompt_text.lower()
    if any(k in prompt_lower for k in ("yaml", "config", "配置文件")):
        return "yaml-config"
    if any(k in prompt_lower for k in ("审查", "review", "critique")) and file_count <= 2:
        return "review"
    if any(k in prompt_lower for k in ("批判", "深度批判", "深度分析")):
        return "text-critique"
    if any(k in prompt_lower for k in ("分析", "analyze")) and file_count <= 2:
        return "text-analysis"
    if file_count > 3 or any(k in prompt_lower for k in ("个文件", "个技能文件", "创建 10", "创建 5", "创建 6", "创建 7", "创建 8", "创建 9")):
        return "multi-file"
    if any(k in prompt_lower for k in ("集成", "integrat", "修改", "workflow")):
        return "integration"
    return "code-generation"


# ── 自测 ────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        profiler = TaskProfiler(tmpdir)

        # 模拟记录几次任务
        profiler.record("T1-skills", "code-generation", "deepseek-v4-pro", "coding",
                        estimated_minutes=5, actual_minutes=3.8, token_count=52500, file_count=1, status="completed")
        profiler.record("T2-multi", "multi-file", "deepseek-v4-pro", "coding",
                        estimated_minutes=12, actual_minutes=11.5, token_count=79600, file_count=10, status="completed")
        profiler.record("T3-config", "yaml-config", "deepseek-v4-pro", "coding",
                        estimated_minutes=5, actual_minutes=7.5, token_count=59900, file_count=2, status="completed")
        profiler.record("T4-review", "review", "deepseek-v4-pro", "reflection",
                        estimated_minutes=5, actual_minutes=5.5, token_count=52100, file_count=1, status="completed")
        profiler.record("T5-timeout", "text-analysis", "deepseek-v4-pro", "decomposition",
                        estimated_minutes=3, actual_minutes=8.5, token_count=39400, file_count=1, status="timeout")

        print(profiler.summary())
        print()

        # 测试校准
        window = profiler.calibrate_window("code-generation", "deepseek-v4-pro", base_minutes=5)
        print(f"\n校准: code-generation, base=5min → window={window}")
        window2 = profiler.calibrate_window("yaml-config", "deepseek-v4-pro", base_minutes=3)
        print(f"校准: yaml-config, base=3min → window={window2}")

        # 测试分类
        tests = [
            ("创建 10 个技能文件", "multi-file"),
            ("创建 YAML 配置文件", "yaml-config"),
            ("代码审查", "review"),
            ("深度批判 R3 方案", "text-critique"),
        ]
        for prompt, expected in tests:
            result = classify_task(prompt)
            status = "✅" if result == expected else f"❌ (expected {expected})"
            print(f"  {status} classify({prompt!r}) = {result}")

        print("\n✅ TaskProfiler 自测全部通过")
