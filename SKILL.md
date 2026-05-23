---
name: auto-coding-v3
description: "智能自主编码系统 v3.7-discipline — 全子代理架构 + 分阶段技能注入。支持 8 步循环、Reviewer 否决权、复杂度自动分级、Risk Scorecard 量化检测。触发词: auto-coding, 写代码, 开发, coding, karpathy"
license: MIT
---

# Auto-Coding v3.7.0

## 🔴 执行铁律

### 铁律 1: 自动推进，不中途停下
启动后连续完成所有阶段。只在 3 种情况打断: (1) 需求不明确 (2) 多方案需选择 (3) 安全审批。

### 铁律 2: 全子代理化，主会话只做监工
所有干活用子代理执行。主会话职责: 分阶段派活、检查文件质量、打回重写、交付结果。

### 铁律 3: 每步输出，不攒到最后
每阶段完成后立刻输出结果（当前阶段、模型、做了什么、发现了什么），然后直接进入下一阶段。

---

## 📋 8 步循环流程 + 技能注入

```
设计 → 分解 → 编码 → 测试 → 反思 → 优化 → 验证 → 输出
  ↑_______________________________________↓
              迭代 (最多 3 次)
```

| 步骤 | 阶段 | 注入技能 | 模型 | 职责 |
|------|------|---------|------|------|
| 1 | **设计** | `grill-with-docs` | `deepseek-v4-pro` | 需求对齐、技术方案 |
| 2 | **分解** | `decomposition` | `deepseek-v4-pro` | 任务拆解、依赖分析 |
| 3 | **编码** | `tdd` | `deepseek-v4-pro` | TDD 红-绿-重构 |
| 4 | **测试** | `testing` | `deepseek-v4-pro` | 边界覆盖、回归检测 |
| 5 | **反思** | `zoom-out` + `code-review` | `deepseek-v4-pro` | 审查、🔴🟡💭 分级 |
| 6 | **优化** | `optimize` | `deepseek-v4-pro` | 推理重构 |
| 7 | **验证** | `verification` | `deepseek-v4-pro` | 交付验证 |
| 8 | **输出** | — | — | 交付物 |

> **注入规则**: 每阶段 ≤2 技能文件，全局文件（`risk-scorecard` + `discipline-meta`）随首次注入附带。注入失败不阻塞流程。
>
> **Reviewer 否决权**: 审查发现 🔴 阻塞项（安全漏洞、不符合需求、过度设计）→ 触发重写，最多 3 次迭代。
> 详细见: `skills/code-review.skill.md`
>
> **调试子流程**: 测试失败或否决时触发 6 阶段调试（反馈循环→复现→假设→插桩→修复→清理）。
> 详细见: `skills/diagnose.skill.md`

---

## ⚡ 复杂度自动分级

| 等级 | 特征 | 阶段数 | 典型耗时 |
|------|------|--------|---------|
| **A (Micro)** | 单函数、Bug 修复 | 编码→测试→验证 (3) | <2 分钟 |
| **B (Feature)** | 模块开发、单 API | 设计→编码→测试→验证 (4) | 2-5 分钟 |
| **C (System)** | 完整系统、多文件重构 | 设计→分解→编码→测试→反思→优化→验证 (7) | 5-15 分钟 |

> A 级至少注入 `grill-with-docs`（需求确认部分）。连续 2 次阻塞自动升级为 B 级。

---

## 🤖 模型分配 + 降级

| 阶段 | 首选 | Fallback 1 | Fallback 2 |
|------|------|-----------|-----------|
| 设计/分解 | `deepseek-v4-pro` | `MiMo v2.5 Pro` | — |
| 编码/测试 | `deepseek-v4-pro` | `MiMo v2.5 Pro` | — |
| 审查/优化 | `deepseek-v4-pro` | `MiMo v2.5 Pro` | — |
| 验证 | `deepseek-v4-pro` | `MiMo v2.5 Pro` | — |

**降级原则**: 优先同级别 → 降一级 → 记入日志。

---

## 📝 子代理铁律

所有子代理禁止输出完整内容到对话:

```
✅ {阶段}完成
📄 输出文件: {file1}, {file2}, ...
💡 一句话结论: {核心结论}
```

---

## 🧠 Karpathy 铁律（精简）

1. **思考优先**: 不假设，模糊需求列出假设或直接提问
2. **极简主义**: 最少代码解决问题，自检"200 行能否缩到 50 行"
3. **手术刀修改**: 只改必须改的，不顺手重构，遵循现有风格
4. **目标导向**: 先定义 Done 标准再编码，验证通过才算完成

---

## 📁 技能文件索引

| 技能文件 | 注入阶段 | 职责 |
|---------|---------|------|
| `skills/grill-with-docs.skill.md` | Step 1 设计 | 需求对齐、结构化追问、CONTEXT.md 维护 |
| `skills/decomposition.skill.md` | Step 2 分解 | 任务拆解纪律、依赖分析、粒度检查 |
| `skills/tdd.skill.md` | Step 3 编码 | TDD 红-绿-重构循环、垂直切片规则 |
| `skills/testing.skill.md` | Step 4 测试 | 测试策略、边界覆盖、回归检测 |
| `skills/zoom-out.skill.md` | Step 5 反思 | 全局视角、跨模块依赖分析 |
| `skills/code-review.skill.md` | Step 5 反思 | Reviewer 审查、🔴🟡💭 分级、Reviewer 否决权 |
| `skills/optimize.skill.md` | Step 6 优化 | 重构纪律、性能优化检查清单 |
| `skills/verification.skill.md` | Step 7 验证 | 交付验证清单、阶段聚合 |
| `skills/diagnose.skill.md` | 调试子流程 | 6 阶段系统化调试 |
| `skills/improve-architecture.skill.md` | Step 8.5 | 架构健康检查、深层耦合发现 |
| `skills/risk-scorecard.skill.md` | 全局（首次附带） | Risk Scorecard 五元组、公用信号检测规则 |
| `skills/discipline-meta.skill.md` | 全局（首次附带） | 元规则、量化上限、override 流程 |

---

## 📦 使用示例

- **A 级**: "写一个 Python 函数计算两个列表的交集" → 编码→测试→验证
- **B 级**: "帮我实现一个 REST API，支持用户注册和登录" → 设计→编码→测试→验证
- **C 级**: "从零搭建一个博客系统，支持文章发布和评论" → 完整 7 阶段

---

## ⚙️ 项目配置

- **状态持久化**: `.auto-coding/state.json` — session 中断自动从上次阶段恢复
- **审批策略**: `.auto-coding/rules.yaml` — 自定义 auto_approve / require_approval
- **阶段日志**: `.auto-coding/logs/{order}-{phase}.log` — 每个阶段独立可追溯

---

*v3.7.0 · 2026-05-22*
