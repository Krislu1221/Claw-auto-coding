---
name: auto-coding-v3
description: "智能自主编码系统 v3.7.7 — 全子代理架构 + 分阶段技能注入。支持 8 步循环、Reviewer 否决权、复杂度自动分级、Risk Scorecard 量化检测。触发词: /auto-coding, auto-coding, 自动编码, 自主编码"
license: MIT
---

# Auto-Coding v3.7.7 - 智能自主编码系统

## 设计理念

### 为什么需要 Auto-Coding

把"写代码"这件事交给 AI，最大的问题不是 AI 不会写，而是**AI 写了就忘了**：

- 写完不测试，或者测试只走 happy path
- 改 A 模块时顺手重构了 B 模块，引入新 bug
- 做了需求没说的"额外功能"，过度设计
- 没有 review 自己代码的习惯，低级错误反复出现

Auto-Coding 的本质是**用结构化流程替代人类的代码纪律**。不是"让 AI 写得更好"，而是"让 AI 像有经验的工程师一样工作"：先设计后编码、测试驱动、自己审查自己、迭代修改、验证交付。每一个阶段都是独立子 Agent，换模型、换人格、换思维方式，模拟代码评审的对抗效果。

### 核心设计原则

1. **全子代理化** — 每个阶段独立 sessions_spawn，主会话只做监工：派活 → 检查文件 → 决定通过/打回
2. **分阶段技能注入** — 每个阶段只注入 ≤2 个技能文件（Prompt Engineering），不撑爆上下文
3. **Pro→Flash 分层路由** — 推理/设计/审查用 Pro，编码/执行/验证用 Flash，成本节省 ~50%
4. **量化防御** — Risk Scorecard 五元组 + 冷却窗口，自动检测"跳过测试""引入不必要文件"等反模式
5. **自动推进不中断** — 只在需求不明确、多方案需选择、安全审批三种情况暂停

---

## 8 步循环流程

```
设计 → 分解 → 编码 → 测试 → 反思 → 优化 → 验证 → 输出
  ↑_______________________________________↓
              迭代 (最多 3 次)
```

| 步骤 | 阶段 | 注入技能 | 默认模型 | 核心职责 |
|------|------|---------|---------|---------|
| 1 | **设计** | `grill-with-docs` | Pro | 需求对齐、反推缺失上下文、技术方案选型 |
| 2 | **分解** | `decomposition` | Pro | 任务原子化、依赖排序、Done 标准定义 |
| 3 | **编码** | `tdd` | Flash | TDD 红-绿-重构循环、垂直切片 |
| 4 | **测试** | `testing` | Flash | 边界覆盖、回归检测、异常路径 |
| 5 | **反思** | `zoom-out` + `code-review` | Pro | 全局视角审查、🔴🟡💭 分级、否决权 |
| 6 | **优化** | `optimize` | Pro | 推理重构、性能优化、Karpathy 极简检查 |
| 7 | **验证** | `verification` | Flash | 交付验证清单、契约一致性自检 |
| 8 | **输出** | — | — | 交付物聚合、变更摘要 |

### 迭代规则

- 反思发现 🔴 阻塞项（安全漏洞、不符合需求、过度设计）→ 触发重写
- 重写后再次进入反思，最多 3 次迭代
- 第 3 次仍阻塞 → 标记失败，保留最后一次代码供人工介入

### 调试子流程

测试失败或 Reviewer 否决时，自动触发 6 阶段系统化调试：
```
反馈循环 → 复现 → 假设 → 插桩 → 修复 → 清理
```
每步都有独立技能文件约束（`skills/diagnose.skill.md`），防止"改改试试看"的随机调试。

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                  AutoCodingWorkflowEnhanced                     │
├─────────────────────────────────────────────────────────────────┤
│  Complexity   │  Skill Injector  │  Model Auto    │  Task        │
│  Analyzer     │  (12 技能)       │  Router        │  Profiler    │
│  (ABC 分级)   │                  │  (Pro→Flash)   │  (窗口校准)   │
├───────────────┼──────────────────┼────────────────┼──────────────┤
│  Scorecard    │  Approval Rules  │  State Manager │  Reviewer     │
│  Engine       │  (YAML 配置)     │  (断点续传)     │  Worker       │
│  (五元组检测)  │                  │                │  (否决权)     │
└─────────────────────────────────────────────────────────────────┘
```

### 1. 复杂度自动分级

根据需求内容自动判断任务复杂度，决定执行哪些阶段：

| 等级 | 特征 | 执行阶段 | 典型耗时 |
|------|------|---------|---------|
| **A (Micro)** | 单函数、Bug 修复、小于 50 行 | 编码→测试→验证 | <2 分钟 |
| **B (Feature)** | 模块开发、单 API、涉及 3 个以下文件 | 设计→编码→测试→验证 | 2-5 分钟 |
| **C (System)** | 完整系统、多文件重构、架构调整 | 完整 7 阶段 | 5-15 分钟 |

**自动升级机制**: 连续 2 次 Reviewer 阻止通过 → 自动升一级（A→B, B→C），确保充分的设计和审查。

### 2. Model Auto Router — Pro→Flash 双层路由

```
┌─ Phase Routing Table ─┐    ┌─ Category Override ─┐    ┌─ Context Gate ─┐
│ design       → Pro     │    │ integration → Pro    │    │ >50k token     │
│ reflection   → Pro     │    │ text-critique → Pro  │    │ → force Pro    │
│ optimize     → Pro     │    │                       │    │ (1M 窗口优势)  │
│ coding       → Flash   │    │                       │    │                │
│ testing      → Flash   │    │                       │    │                │
│ verification → Flash   │    │                       │    │                │
└────────────────────────┘    └───────────────────────┘    └────────────────┘
         ↓                           ↓                          ↓
                 三层决策 → 最终 (model, thinking_level)
```

- **Pro 做"大脑"**：设计、分解、反思（审查）、优化（重构）
- **Flash 做"手"**：编码、测试、验证（执行写入）
- **例外覆盖**：集成修改（非独立创建）→ 升回 Pro；大上下文 >50k token → Pro 的 1M 窗口优势
- **预估成本节省**：~50%（vs 全 Pro）

### 3. Skill Injector — 分阶段技能注入

12 个独立技能文件，按阶段精确注入，每阶段 ≤2 个，避免上下文溢出：

```
Phase Skill Map:
  design         → grill-with-docs
  decomposition  → decomposition
  coding         → tdd
  testing        → testing
  reflection     → zoom-out + code-review  (≤2)
  optimize       → optimize
  verification   → verification
  diagnose       → diagnose
  architecture   → improve-architecture
  ───────────────────────────────────────
  global         → risk-scorecard + discipline-meta
                 (首次注入时自动附带)
```

**降级策略**: 技能文件缺失或解析失败 → 跳过该技能、记录警告、不阻塞流程。

### 4. Risk Scorecard 引擎 — 量化防御

五元组检测模型，每阶段执行后自动扫描：

| 维度 | 信号示例 | 默认阈值 |
|------|---------|---------|
| **完整性** | `testing_phase_executed == false` | 🔴 阻塞 |
| **一致性** | `modified_file_count > expected_file_count` | 🟡 警告 |
| **安全性** | `hardcoded_secret_detected` | 🔴 阻塞 |
| **简洁性** | `extra_features_added > 0` | 🟡 警告（Karpathy 铁律） |
| **流程纪律** | `zoom_out_executed == false and modified_file_count > 3` | 🟡 警告 |

**冷却窗口**: 同一类失败 24h 内第 3 次触发 → 静默，防告警疲劳。

**表达式引擎**: AST 安全求值，支持 `and/or/not` + 比较运算符，零 `eval()` 调用。

### 5. Task Profiler — 动态窗口校准

记录每次子 Agent 实际耗时，按 category/model/phase 计算校准系数：

```
窗口 = 静态预估 × adjust_factor × model_factor × risk_buffer
```

- **adjust_factor**: 该 category 的历史实际/预估比值滑动平均
- **model_factor**: 模型基准耗时比（Flash ~0.3 vs Pro ~1.0）
- **risk_buffer**: phase 中断风险指数（设计低风险、反思中风险）

### 6. Reviewer 否决权

审查阶段由独立 Reviewer Worker 执行，拥有否决权：

- **🔴 阻塞项**: 安全漏洞、不符合需求、过度设计 → 必须重写
- **🟡 警告项**: 缺少测试、命名不规范、潜力冗余 → 建议修改
- **💭 观察项**: 风格偏好、可优化点 → 记录不阻塞

### 7. 状态持久化 — 断点续传

```
.auto-coding/
├── state.json      # 当前阶段、已完成步骤、信号值快照
├── workflow.yaml   # 流程配置（模型覆盖、超时、迭代次数）
├── rules.yaml      # 审批策略（auto_approve / require_approval）
├── .profile.json   # Task Profiler 历史数据
└── logs/           # 每阶段独立日志
    ├── 01-design.log
    └── ...
```

session 中断后重新启动自动从 `state.json` 恢复，跳过已完成阶段。

---

## Karpathy 铁律

代码层面的行为约束，所有编码子 Agent 必须遵守：

1. **思考优先**: 不假设，模糊需求列出假设或直接提问
2. **极简主义**: 最少代码解决，自检"200 行能否缩到 50 行"
3. **手术刀修改**: 只改必须改的，不顺手重构，遵循现有风格
4. **目标导向**: 先定义 Done 标准再编码，验证通过才算完成
5. **TDD 纪律**: 先写测试（红）→ 实现（绿）→ 重构，不跳过

---

## 12 技能文件体系

| 技能文件 | 注入阶段 | 职责 |
|---------|---------|------|
| `grill-with-docs` | 设计 | 需求对齐、结构化追问、CONTEXT.md 维护 |
| `decomposition` | 分解 | 任务原子化、依赖分析、粒度检查 |
| `tdd` | 编码 | TDD 红-绿-重构循环、垂直切片规则 |
| `testing` | 测试 | 测试策略、边界覆盖、回归检测 |
| `zoom-out` | 反思 | 全局视角、跨模块依赖分析 |
| `code-review` | 反思 | 🔴🟡💭 分级审查、否决权 |
| `optimize` | 优化 | 重构纪律、性能优化检查清单 |
| `verification` | 验证 | 交付验证清单、契约一致性自检 |
| `diagnose` | 调试子流程 | 6 阶段系统化调试 |
| `improve-architecture` | 架构检查 | 架构健康检查、深层耦合发现 |
| `risk-scorecard` | 全局 | 五元组检测、信号定义、阈值规则 |
| `discipline-meta` | 全局 | 元规则、量化上限、override 流程 |

---

## 容错与降级

| 场景 | 策略 |
|------|------|
| 技能文件缺失 | 跳过该技能、记录警告、继续执行 |
| 模型不可用 | 同层降级（Pro→Pro 备选, Flash→Flash 备选）→ 跨层降级 |
| 子 Agent 超时 | 记录 failure + 重试 2 次 |
| 审查连续 2 次阻塞 | 自动升级复杂度 → 回到设计重新来 |
| 第 3 次迭代仍阻塞 | 标记失败、保留最后代码、报告给用户 |
| session 中断 | 重启时从 state.json 恢复、跳过已完成阶段 |

---

## v3.7 vs v3.6

| 维度 | v3.6 | v3.7 |
|------|------|------|
| **架构** | 单进程串行、多角色 Prompt | **全子代理架构**、每阶段独立 Agent |
| **模型路由** | 阶段硬编码 | **Pro→Flash 双层自动路由**（成本节省 ~50%） |
| **防御机制** | 三重防错自检 | **Risk Scorecard 五元组 + 冷却窗口** |
| **技能注入** | 内嵌 8 个 Agent Soul | **12 独立技能文件、按阶段注入** |
| **超时控制** | 固定超时 | **Task Profiler 动态校准** |
| **断点续传** | 基础 state.json | **完整恢复 + 日志追踪** |
| **Reviewer** | 审查无否决权 | **独立 Worker + 🔴阻塞 → 强制重写** |

---

## 使用策略

### 本地（完整能力）
```python
from workflow_enhanced import AutoCodingWorkflowEnhanced
wf = AutoCodingWorkflowEnhanced(
    requirements="实现用户登录功能",
    project_dir="./my-project"
)
await wf.run()
```

### 触发词
`/auto-coding` | `auto-coding` | `自动编码` | `自主编码`

---

*v3.7.7 · 2026-05-24*
