"""
Skill Injector — 按阶段注入技能文件的 prompt 拼接器。

职责：
- 根据 phase 名称返回该阶段需要的技能文件内容拼接
- 缓存已加载的技能文件（同一文件只读一次）
- 降级策略：文件不存在/解析失败时返回空字符串 + 记录警告，不发异常
- 全局文件（risk-scorecard + discipline-meta）首次注入时自动附带
- 断言检查：每阶段技能数不超过 2 个

用法：
    injector = SkillInjector()
    prompt, meta = injector.inject_for_phase("coding")
    # prompt: 拼接好的技能内容
    # meta: {"skills": [...], "token_estimate": int}
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 阶段 → 技能映射表 ──────────────────────────────────────────────

PHASE_SKILL_MAP: Dict[str, List[str]] = {
    "design":            ["grill-with-docs"],
    "decomposition":     ["decomposition"],
    "coding":            ["tdd"],
    "testing":           ["testing"],
    "reflection":        ["zoom-out", "code-review"],
    "optimize":          ["optimize"],
    "verification":      ["verification"],
    "diagnose":          ["diagnose"],
    "architecture_check":["improve-architecture"],
}

# 全局技能文件 — 首次注入时自动附带
GLOBAL_SKILLS: List[str] = ["risk-scorecard", "discipline-meta"]

# 每阶段允许的最大技能数
MAX_SKILLS_PER_PHASE: int = 2


class SkillInjector:
    """按阶段注入技能文件的 prompt 拼接器。

    核心能力：
    - inject_for_phase(phase) → 返回拼接后的 prompt + 元信息
    - load_global() → 加载全局文件
    - get_all_skills() → 列出所有已知技能文件名
    - 内置缓存 + 降级策略
    """

    def __init__(self, skills_dir: Optional[str] = None) -> None:
        """初始化注入器。

        Args:
            skills_dir: 技能文件所在目录。默认自动推断为本文件同级目录下的
                        skills/ 子目录。
        """
        if skills_dir is None:
            skills_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "skills"
            )
        self._skills_dir: str = skills_dir

        # 文件内容缓存：{ 技能名: 文件内容 }
        self._cache: Dict[str, str] = {}

        # 全局文件是否已加载过
        self._global_loaded: bool = False

        # 启动时校验阶段映射表
        self._validate_phase_map()

    # ── 公开 API ──────────────────────────────────────────────────

    def inject_for_phase(self, phase: str) -> Tuple[str, dict]:
        """为指定阶段注入技能 prompt。

        Args:
            phase: 阶段名称，必须是 PHASE_SKILL_MAP 中的 key。

        Returns:
            (拼接后的 prompt 文本, 注入元信息)
            元信息格式：{"skills": [已加载技能名列表], "token_estimate": int}

        Raises:
            ValueError: phase 不在映射表中时抛出。
        """
        if phase not in PHASE_SKILL_MAP:
            raise ValueError(
                f"未知阶段 '{phase}'，已知阶段: {list(PHASE_SKILL_MAP.keys())}"
            )

        skill_names: List[str] = PHASE_SKILL_MAP[phase]

        # 断言检查：每阶段技能数 ≤ 2
        if len(skill_names) > MAX_SKILLS_PER_PHASE:
            logger.warning(
                "阶段 '%s' 的技能数 %d 超过上限 %d，这违反了设计约束",
                phase, len(skill_names), MAX_SKILLS_PER_PHASE,
            )

        loaded_names: List[str] = []
        parts: List[str] = []

        # 首次注入时附带全局文件
        if not self._global_loaded:
            global_content = self.load_global()
            if global_content:
                parts.append(global_content)
            loaded_names.extend(GLOBAL_SKILLS)

        # 加载阶段技能
        for name in skill_names:
            content = self._load_skill(name)
            if content:
                parts.append(content)
                loaded_names.append(name)

        combined = "\n\n---\n\n".join(parts) if parts else ""

        # token 估算：字符数 / 4（粗略经验值）
        token_estimate = len(combined) // 4 if combined else 0

        meta = {
            "skills": loaded_names,
            "token_estimate": token_estimate,
            "phase": phase,
        }

        return combined, meta

    def load_global(self) -> str:
        """加载全局技能文件（risk-scorecard + discipline-meta）。

        仅在首次调用时真正读取，后续调用返回缓存结果。
        设置 _global_loaded 标记以避免重复注入。

        Returns:
            拼接后的全局技能内容。
        """
        if self._global_loaded:
            # 已经加载过，返回缓存
            cached_parts = [self._cache.get(name, "") for name in GLOBAL_SKILLS]
            return "\n\n---\n\n".join(p for p in cached_parts if p)

        parts: List[str] = []
        for name in GLOBAL_SKILLS:
            content = self._load_skill(name)
            if content:
                parts.append(content)

        self._global_loaded = True
        return "\n\n---\n\n".join(parts) if parts else ""

    def get_all_skills(self) -> List[str]:
        """返回所有已知技能文件名（供主 SKILL.md 索引或文档生成使用）。

        Returns:
            全局技能 + 所有阶段技能的并集（去重）。
        """
        all_skills: set = set(GLOBAL_SKILLS)
        for skills in PHASE_SKILL_MAP.values():
            all_skills.update(skills)
        return sorted(all_skills)

    def clear_cache(self) -> None:
        """清空文件缓存并重置全局加载标记。

        用于测试或需要重新加载技能文件的场景。
        """
        self._cache.clear()
        self._global_loaded = False

    # ── 内部方法 ──────────────────────────────────────────────────

    def _load_skill(self, name: str) -> str:
        """加载单个技能文件（带缓存 + 降级）。

        Args:
            name: 技能文件名（不含 .skill.md 后缀）。

        Returns:
            文件内容，读取失败时返回空字符串。
        """
        # 缓存命中
        if name in self._cache:
            return self._cache[name]

        filename = f"{name}.skill.md"
        filepath = os.path.join(self._skills_dir, filename)

        try:
            if not os.path.isfile(filepath):
                logger.warning(
                    "技能文件不存在: %s（路径: %s）",
                    filename, filepath,
                )
                self._cache[name] = ""
                return ""

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                logger.warning("技能文件为空: %s", filename)
                self._cache[name] = ""
                return ""

            self._cache[name] = content
            logger.debug("已加载技能: %s (%d 字符)", name, len(content))
            return content

        except OSError as exc:
            logger.warning(
                "读取技能文件失败: %s — %s", filepath, exc
            )
            self._cache[name] = ""
            return ""
        except Exception as exc:
            logger.warning(
                "加载技能文件时发生未预期错误: %s — %s", filename, exc
            )
            self._cache[name] = ""
            return ""

    def _validate_phase_map(self) -> None:
        """校验阶段映射表。

        检查项：
        - 每个 key 有对应的 list
        - 每个 list 中的技能文件存在
        - 触发警告但不抛异常（降级友好）
        """
        for phase, skills in PHASE_SKILL_MAP.items():
            if not isinstance(skills, list):
                logger.warning(
                    "阶段 '%s' 的技能配置不是列表类型: %s", phase, type(skills)
                )
                continue

            for name in skills:
                filepath = os.path.join(
                    self._skills_dir, f"{name}.skill.md"
                )
                if not os.path.isfile(filepath):
                    logger.warning(
                        "阶段 '%s' 引用的技能文件不存在: %s.skill.md", phase, name
                    )

