# Auto-Coding v3.7-discipline

**版本**: v3.7-discipline  
**更新日期**: 2026-05-22

---

## 概述

Auto-Coding 是一个智能自主编码系统，通过 **全子代理架构 + 分阶段技能注入**，完成从需求到代码的完整开发流程：

```
设计 → 分解 → 编码 → 测试 → 反思 → 优化 → 验证 → 输出
  ↑_______________________________________↓
              迭代 (最多 3 次)
```

**v3.7-discipline 核心特性**:
- 🔴 **Risk Scorecard** — 五元组量化检测，每阶段自动输出风险评分
- 📦 **技能模块化注入** — 12 个独立技能文件，按阶段动态注入（≤2 个/阶段）
- 🛡️ **Reviewer 否决权** — 审查发现 🔴 阻塞项自动触发重写（最多 3 次迭代）
- 🐛 **6 阶段调试子流程** — 测试失败/否决时自动触发系统化诊断
- ⚡ **复杂度自动分级** — A/B/C 三级，按需跳过阶段
- 🤖 **模型降级链** — deepseek-v4-pro → MiMo v2.5 Pro，自动 fallback

---

## 复杂度自动分级

| 等级 | 特征 | 阶段数 | 典型耗时 |
|------|------|--------|---------|
| **A (Micro)** | 单函数、Bug 修复 | 编码→测试→验证 (3) | <2 分钟 |
| **B (Feature)** | 模块开发、单 API | 设计→编码→测试→验证 (4) | 2-5 分钟 |
| **C (System)** | 完整系统、多文件重构 | 完整 7 阶段 | 5-15 分钟 |

---

## 8 步循环 + 技能注入

| 步骤 | 阶段 | 注入技能 | 职责 |
|------|------|---------|------|
| 1 | **设计** | `grill-with-docs` | 需求对齐、技术方案 |
| 2 | **分解** | `decomposition` | 任务拆解、依赖分析 |
| 3 | **编码** | `tdd` | TDD 红-绿-重构 |
| 4 | **测试** | `testing` | 边界覆盖、回归检测 |
| 5 | **反思** | `zoom-out` + `code-review` | 审查、🔴🟡💭 分级 |
| 6 | **优化** | `optimize` | 推理重构 |
| 7 | **验证** | `verification` | 交付验证 |
| 8 | **输出** | — | 交付物 |

---

## 技能文件索引

| 技能文件 | 注入阶段 | 职责 |
|---------|---------|------|
| `skills/grill-with-docs.skill.md` | Step 1 设计 | 需求对齐、结构化追问、CONTEXT.md 维护 |
| `skills/decomposition.skill.md` | Step 2 分解 | 任务拆解纪律、依赖分析、粒度检查 |
| `skills/tdd.skill.md` | Step 3 编码 | TDD 红-绿-重构循环、垂直切片规则 |
| `skills/testing.skill.md` | Step 4 测试 | 测试策略、边界覆盖、回归检测 |
| `skills/zoom-out.skill.md` | Step 5 反思 | 全局视角、跨模块依赖分析 |
| `skills/code-review.skill.md` | Step 5 反思 | Reviewer 审查、🔴🟡💭 分级、否决权 |
| `skills/optimize.skill.md` | Step 6 优化 | 重构纪律、性能优化检查清单 |
| `skills/verification.skill.md` | Step 7 验证 | 交付验证清单、阶段聚合 |
| `skills/diagnose.skill.md` | 调试子流程 | 6 阶段系统化调试 |
| `skills/improve-architecture.skill.md` | Step 8.5 | 架构健康检查、深层耦合发现 |
| `skills/risk-scorecard.skill.md` | 全局（首次附带） | Risk Scorecard 五元组 |
| `skills/discipline-meta.skill.md` | 全局（首次附带） | 元规则、量化上限、override 流程 |

---

## 快速开始

### 环境要求

- OpenClaw 2026.5.7+
- deepseek-v4-pro 或 MiMo v2.5 Pro provider 已配置

```bash
openclaw --version
openclaw models list
```

### 基本使用

```python
from workflow_enhanced import AutoCodingWorkflowEnhanced

workflow = AutoCodingWorkflowEnhanced(
    requirements="实现用户登录功能",
    project_dir="./my-project",
    resume=True,
)
await workflow.run()
```

---

## 模型分配 + 降级

| 阶段 | 首选 | Fallback |
|------|------|----------|
| 所有阶段 | `deepseek-v4-pro` | `MiMo v2.5 Pro` |

**降级原则**: 优先同级别 → 降一级 → 记入日志。

---

## Karpathy 铁律

1. **思考优先**: 不假设，模糊需求列出假设或直接提问
2. **极简主义**: 最少代码解决问题，自检"能不能再短"
3. **手术刀修改**: 只改必须改的，不顺手重构，遵循现有风格
4. **目标导向**: 先定义 Done 标准再编码，验证通过才算完成

---

## 项目配置

- **状态持久化**: `.auto-coding/state.json` — session 中断自动从上次阶段恢复
- **审批策略**: `.auto-coding/rules.yaml` — 自定义 auto_approve / require_approval
- **阶段日志**: `.auto-coding/logs/{order}-{phase}.log` — 每个阶段独立可追溯

---

## 更新日志

| 版本 | 日期 | 关键变更 |
|------|------|---------|
| **v3.7-discipline** | 2026-05-22 | Risk Scorecard 五元组 + 12 技能模块化注入 + Reviewer 否决权 + 调试子流程 |
| v3.6.1 | 2026-05-16 | 猫王审查 Bugfix - running 标记误删修复 + 死代码清理 + ClawHub 发布合规 |
| v3.6.0 | 2026-05-15 | 动态状态监控机制 + 状态同步清理 + 5分钟进度通报 |
| v3.5.0 | 2026-05-15 | Heartbeat 双轨状态同步机制 |
| v3.4.1 | 2026-05-13 | 统一模型降级 + 三重防错自检 + PII 清理 |
| v3.4 | 2026-05-11 | 5 项嵌入式工程技能 |
| v3.3 | 2026-05-09 | 8 个 Soul + 按阶段模型分配 + 状态持久化 |

---

## 👤 作者

Kris Lu <krislu666@foxmail.com>

## 📄 许可

MIT License

---

*Auto-Coding v3.7-discipline · 2026-05-22 · 虾软 🦐*
