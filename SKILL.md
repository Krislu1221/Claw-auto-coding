---
name: auto-coding-v3
description: "智能自主编码系统 v3.6.1 - 全子代理架构 + MiMo 优先。支持 8 步循环、Reviewer 否决权、复杂度自动分级、状态持久化、阶段日志可追溯、子代理只写文件不刷屏。触发词: auto-coding, 写代码, 开发, coding, karpathy"
license: MIT
---

# Auto-Coding v3.6.1 - 全子代理架构 + MiMo 优先

## 🔴 执行铁律(必须遵守)

### 铁律 1:自动推进,不中途停下
**启动后连续完成所有阶段,不要每个阶段结束后停下来等用户说"继续"。**
只有以下 3 种情况才打断用户:
1. 需求不明确,需要澄清
2. 有多个技术方案,需要用户选择
3. 触发了安全审批,需要用户确认

### 铁律 2:全子代理化,主会话只做监工
**所有干活的阶段全用子代理执行**,主会话(我)只做:分阶段派活、检查文件质量、打回重写、交付结果。

每阶段子代理用最优模型,实测 MiMo 最快最好:
| 阶段 | 推荐模型 | 实测表现 |
|------|---------|---------|
| 设计/分解 | **MiMo v2.5 Pro** | 8 秒完成,简洁精准 |
| 编码 | **MiMo v2.5 Pro** | 56 秒写完 5 个文件,还听话 |
| 审查 | **DeepSeek v4 Pro** | 逻辑推理强，找茬专业户 |
| 优化 | **DeepSeek v4 Pro** | 推理深，适合重构和优化（MiMo 做 fallback） |

### 铁律 3:每步输出,不攒到最后
**每个阶段完成后立刻输出该阶段的结果,不要把所有阶段攒到最后一次性发。**
用户应该看到:
- 当前是哪个阶段、用了什么模型
- 该阶段做了什么、发现了什么
- 然后直接进入下一阶段

---

## 简介

基于 DeepSeek + MiMo 双模型驱动的编码系统,通过 8 个角色 Soul + 双模型(MiMo/DeepSeek) 按阶段切换,完成从需求到代码的完整开发流程。

**核心特性**:
1. **全子代理架构**：所有干活阶段全用子代理，主会话只做监工 + 质量把关
2. **8 步循环流程**:设计→分解→编码→测试→反思→优化→验证→输出
3. **Reviewer 否决权**:审查发现 🔴 阻塞项 → 强制触发重写
4. **复杂度自动分级**:A/B/C 三级自动判断,决定走哪些阶段
5. **MiMo 优先模型分配**：实测 MiMo 最快最好，所有生产阶段优先用
6. **状态持久化**:项目级 `.auto-coding/state.json`,session 断了可恢复
7. **阶段日志可追溯**:每个阶段独立写日志，精确知道卡在哪、错误是什么
8. **子代理只写文件不刷屏**：所有产出写磁盘，对话里只输出一句话确认
9. **流程配置化**：项目级 `.auto-coding/workflow.yaml`
10. **审批策略**：项目级 `.auto-coding/rules.yaml`，敏感操作自动拦截
11. **Karpathy 铁律约束**：极简主义 + 手术刀修改
12. **5 项嵌入式工程技能**：grill-with-docs(需求对齐) + tdd(测试驱动) + zoom-out(全局视角) + diagnose(调试纪律) + improve-architecture(架构健康)
13. **v3.6.1 架构升级**：全子代理 + MiMo 优先 + 阶段日志 + 可追溯（含 heartbeat 巡检 bugfix）

---

## 8 步循环流程

```
设计(Design) → 分解(Decomposition) → 编码(Coding) → 测试(Testing)
    ↑____________________________________________________↓
                         反思(Reflection) → 优化(Optimization)
                                                 ↓
验证(Verification) → 输出(Output)
```

**迭代机制**:测试→反思→优化 循环(最多 3 次),Reviewer 否决时触发重写。

| 步骤 | 阶段 | Soul 角色 | 模型（推荐） | 职责 | 嵌入技能 |
|------|------|----------|-------------|------|----------|
| 1 | **设计** | software-architect | `MiMo v2.5 Pro` | 技术方案、架构选型 | 🔥 grill-with-docs |
| 2 | **分解** | software-architect | `MiMo v2.5 Pro` | 任务拆解、依赖管理 | - |
| 3 | **编码** | senior-developer | `MiMo v2.5 Pro` | 核心代码实现 | - |
| 4 | **测试** | api-tester | `MiMo v2.5 Pro` | 功能测试、边界验证 | 🔥 tdd |
| 5 | **反思** | code-reviewer | `deepseek/deepseek-v4-pro` | 代码审查、🔴🟡💭 分级 | 🔥 zoom-out |
| 6 | **优化** | optimizer | `deepseek/deepseek-v4-pro` | 推理重构、性能优化 | - |
| 7 | **验证** | verifier | `MiMo v2.5 Pro` | 交付验证、功能完整性 | - |
| 8 | **输出** | - | - | 交付物生成 |

### Reviewer 否决权(关键机制)

```
编码 → 测试 → 反思(审查)
              ↓
        🔴 有阻塞项?
         ↓ 是
    [否决] → 回到编码(重写)
         ↓ 否
    [通过] → 优化 → 验证
```

- **🔴 阻塞项**(安全漏洞、不符合需求、过度设计)→ **否决**,触发重写
- **🟡 建议项**(性能优化、可读性改进)→ 通过,优化阶段处理
- **💭 小改进**(风格微调)→ 通过,可选处理

**最大重写次数**:3 次迭代内可多次否决,超过则停止。

### 🔥 调试子流程(diagnose)

当测试失败或 Reviewer 否决时,触发 6 阶段调试流程:

```
测试失败/Reviewer 否决
  ↓
Phase 1: 建反馈循环(可复现的 pass/fail 信号)
  ↓
Phase 2: 复现(确认 bug 和描述一致)
  ↓
Phase 3: 假设(3-5 个可证伪假设,排优先级)
  ↓
Phase 4: 插桩(带 [DEBUG-xxx] 标签的定向日志)
  ↓
Phase 5: 修复(先写回归测试再修复)
  ↓
Phase 6: 清理 + 复盘
```

**关键原则**:"先建反馈循环再猜测" - 不建循环就不猜原因。

**调试结束后的动作**:
- 回归测试通过 → 继续主流程
- 发现架构问题 → 触发 improve-codebase-architecture
- 调试超过 5 分钟 → 向用户报告并请求协助

---

## 复杂度自动分级 + 全子代理执行策略

**所有任务全用子代理执行**,主会话只做:分阶段派活、检查质量、打回重写、交付结果。复杂度分级只决定阶段数量,不区分主/子执行模式。

| 等级 | 特征 | 阶段数 | 典型耗时 |
|------|------|--------|---------|
| **A (Micro)** | 单函数、Bug 修复、配置修改 | 3 个阶段(编码 → 测试 → 验证) | < 2 分钟 |
| **B (Feature)** | 模块开发、单文件修改、新 API | 4 个阶段(设计 → 编码 → 测试 → 验证) | 2-5 分钟 |
| **C (System)** | 完整系统、多文件重构、新项目 | 6 个阶段(设计 → 分解 → 编码 → 测试 → 审查 → 优化 → 验证) | 5-15 分钟 |

### 🥷 角色分工(核心架构!)

| 角色 | 谁来做 | 做什么 |
|------|-------|--------|
| **监工 + 质量把关** | **主会话(我)** | 分阶段派活、检查文件、打回重写、交付结果 |
| **干具体活** | **子代理(N 个)** | 写设计、写代码、跑测试、做审查,只写文件,不输出大段内容 |

### 🤖 模型分配(基于实测结论)

| 阶段 | 推荐模型 | 实测表现 |
|------|---------|---------|
| 设计/分解 | **MiMo v2.5 Pro** | 最快、最准、输出最简洁,8 秒搞定 |
| 编码 | **MiMo v2.5 Pro** | 写得又快又好,56 秒写完 5 个文件,还听话 |
| 测试 | **MiMo v2.5 Pro** | 写测试用例快 |
| 审查 | **DeepSeek v4 Pro** | 逻辑推理强，找茬专业户 |
| 优化 | **DeepSeek v4 Pro** | 推理深，适合重构和优化（MiMo 做 fallback） |
| 验证 | **MiMo** | 快就行 |

### 📝 子代理铁律(必须遵守!)

**所有子代理绝对不能把完整内容输出到对话里!** 所有详细内容写到磁盘文件,最后只输出:

```
✅ {阶段}完成
📄 输出文件:{文件路径1}, {文件路径2}, ...
💡 一句话结论:{核心结论}
```

✅ 正确示例:
```
✅ 编码完成
📄 输出文件:main.py, models.py, schemas.py
💡 一句话结论:5 个文件,JWT 认证,密码 bcrypt 哈希
```

❌ 错误示例:
> 「好的,我现在开始设计,首先技术选型是 FastAPI...(以下省略 1000 字)」

**目的**:避免输出太长超时、避免对话被代码刷屏、所有产出都在文件里可追溯。

### 📝 阶段日志(可追溯)

每个阶段独立写日志到 `.auto-coding/logs/{order}-{phase}.log`,方便事后追溯:

```text
[HH:MM:SS] 🚀 开始阶段:{phase}
[HH:MM:SS] 🤖 使用模型:{model}
[HH:MM:SS] 📝 输出完成({tokens} tokens)
[HH:MM:SS] 🛠️ 调用工具:exec pytest
[HH:MM:SS] ❌ 工具失败:错误信息...
[HH:MM:SS] 🔁 重试第 1 次...
[HH:MM:SS] ✅ 阶段完成,耗时:X 秒
```

目录结构:
```
.auto-coding/
├── state.json          # 状态文件
└── logs/
    ├── 01-design.log
    ├── 02-coding.log
    ├── 03-testing.log
    ├── 04-review.log
    ├── 05-optimize.log
    └── 06-verify.log
```

**追溯方法**:出问题直接看对应阶段的日志文件,精确知道卡在哪一步、错误信息是什么。

---

## 模型分配（实测结论）

| 阶段 | 模型 | 实测结论 |
|------|------|---------|
| 设计/分解 | `MiMo v2.5 Pro` | 最快最准，8 秒完成设计 |
| 编码 | `MiMo v2.5 Pro` | 56 秒写完 5 个文件，还听话 |
| 审查 | `deepseek/deepseek-v4-pro` | 逻辑推理强，找茬专业户 |
| 测试 | `MiMo v2.5 Pro` | 写测试用例快 |
| 优化 | `deepseek/deepseek-v4-pro` | 推理深，适合重构 |
| 验证 | `MiMo v2.5 Pro` | 快就行 |

### 关键原则

- **MiMo 优先**：实测 MiMo 速度 + 质量碾压豆包，所有生产阶段优先用
- **要质量不要速度**:不用 `lite` 做主要工作
- **`deepseek/deepseek-v4-pro` 独特价值**:推理深,专用于审查、优化和验证
- **`deepseek/deepseek-v4-pro` 独特价值**:逻辑推理强,专用于审查和优化

### 🔄 Fallback 降级策略（模型不可用时自动切换）

| 阶段 | 首选 | Fallback 1 | Fallback 2 | Fallback 3 |
|------|------|-----------|-----------|-----------|
| 设计/分解 | **MiMo v2.5 Pro** | deepseek/deepseek-v4-pro | - | - |
| 编码 | **MiMo v2.5 Pro** | deepseek/deepseek-v4-pro | - | - |
| 审查 | **deepseek/deepseek-v4-pro** | MiMo v2.5 Pro | - | - |
| 测试 | **MiMo v2.5 Pro** | deepseek/deepseek-v4-pro | - | - |
| 优化 | **deepseek/deepseek-v4-pro** | MiMo v2.5 Pro | - | - |
| 验证 | **MiMo v2.5 Pro** | deepseek/deepseek-v4-pro | - | - |

**降级原则**：
1. 优先换同价位同能力级别的模型
2. 实在不行降一级，只要能完成任务
3. fallback 次数记入日志，方便后续优化调度策略

---

## 8 个内嵌 Agent Soul

| Agent ID | 名称 | 专长 | 模型 |
|----------|------|------|------|
| `engineering-software-architect` | 软件架构师 | 架构设计、DDD | pro |
| `engineering-backend-architect` | 后端架构师 | 分布式系统、数据库 | pro |
| `engineering-senior-developer` | 高级开发工程师 | Python 实现、类型注解 | code |
| `engineering-frontend-developer` | 前端工程师 | React/Vue、组件设计 | code |
| `engineering-code-reviewer` | 代码审查专家 | PR 审查、安全 | deepseek |
| `testing-api-tester` | API 测试工程师 | 接口测试、边界条件 | pro |
| engineering-optimizer | 代码优化工程师 | 优雅重构、性能最优 | deepseek/deepseek-v4-pro |
| testing-verifier | 交付验证工程师 | 功能完整性、边界覆盖 | MiMo v2.5 Pro |

---

## Karpathy 铁律(所有阶段强制执行)

### 1. 思考优先 (Think Before Coding)
- 不假设,遇到模糊需求显式说出假设或直接提问
- 如果有多种理解方式,全部列出

### 2. 极简主义 (Simplicity First)
- 最少代码解决当前问题
- 不添加未被要求的功能、抽象或配置
- **自检**:"如果 200 行能缩减到 50 行,重写它"

### 3. 手术刀式修改 (Surgical Changes)
- 只修改必须修改的地方
- 不碰无关代码,不顺手重构
- 遵循现有代码风格

### 4. 目标导向 (Goal-Driven)
- 定义"Done"标准再编码
- 验证通过才算完成

---

## Reviewer 审查边界(关键约束)

- **需求明确要求的做法优先于极简主义**:如果代码严格按需求实现,不应批评
- **不要在需求明确约束上挑刺**:不要在"需求说怎么做"这件事上批评
- **只审查"实现方式是否符合需求"和"是否有额外内容"**
- **否决标准**:只有 🔴 阻塞项(安全、不符合需求、过度设计)才能否决

---

## 🔥 嵌入式工程技能(v3.4.1 新增)

以下 5 个技能已深度嵌入到 8 步流程的对应阶段,不是独立使用,而是作为流程内建能力。

### 1. Grill-With-Docs(需求对齐)→ 嵌入 Step 1 设计阶段

> 来源:Matt Pocock `grill-with-docs`,解决 AI 编码最大失败模式--需求偏差。

**设计阶段不再"直接出方案",改为结构化追问:**

1. **探索代码库 + 读取 CONTEXT.md**(领域术语表)
2. **逐个问题追问**,一次一个,走完决策树:
   - 目标:解决什么问题?用户是谁?
   - 范围:做什么?不做什么?
   - 行为:正常流程?异常流程?
   - 接口:输入/输出?模块交互?
   - 数据:存储?格式?迁移?
   - 约束:性能?安全?兼容性?
   - 验收:怎么证明做完了?
3. **每个问题给推荐答案**和理由
4. **自动维护 CONTEXT.md**:追问中发现的新术语立即写入
5. **谨慎创建 ADR**:只在"不可逆+令人惊讶+真实权衡"时才创建

**CONTEXT.md 格式**:
```markdown
# 领域术语表

## [术语1]
[精确定义,避免 agent verbose 表达]

## [术语2]
[精确定义]
```

**ADR 创建标准(三条件全满足才创建)**:
1. 不可逆--改主意代价大
2. 令人惊讶--未来读者会问"为什么这样做"
3. 真实权衡--有真正的替代方案

**效果**:
- 需求偏差减少 50%+
- 后续迭代共享统一术语,agent 表达更精准
- 节省 token(术语表比每次解释更简洁)

---

### 2. TDD(测试驱动开发)→ 嵌入 Step 4 测试阶段

> 来源:Matt Pocock `tdd`,红-绿-重构循环。

**测试阶段改为严格的 TDD 循环:**

```
RED:   写一个失败测试 → 测试失败
GREEN: 写最小代码通过 → 测试通过
REFACTOR: 重构 → 测试仍通过
→ 循环下一个切片
```

**核心规则**:
- **垂直切片**:禁止"先写所有测试再写代码"(水平切片会产生垃圾测试)
- **一次一个测试**:只写当前测试需要的最小实现
- **测试行为不测实现**:只验证 public API,不 mock 内部
- **GREEN 才能 REFACTOR**:永远不在 RED 状态重构

**每个循环检查清单**:
```
[ ] 测试描述行为而非实现
[ ] 测试只用公开接口
[ ] 测试能在内部重构后存活
[ ] 代码是为当前测试的最小实现
[ ] 没有添加投机性功能
```

**效果**:
- 测试存活率大幅提升(不会因重构而断)
- 每个测试都有明确目的
- 代码和测试同步演进

---

### 3. Zoom-Out(全局视角)→ 嵌入 Step 5 反思阶段

> 来源:Matt Pocock `zoom-out`,防止"只见树木不见森林"。

**反思阶段先 zoom-out 再审查:**

1. **Zoom-Out**:审查 agent 先跳出当前代码,解释:
   - 这段代码在系统中的位置
   - 和哪些模块交互
   - 调用者是谁
   - 依赖了什么
2. **然后审查**:在理解全局后再审查具体实现

**触发词**:当审查 agent 对代码区域不熟悉时,自动触发 zoom-out。

**效果**:
- 减少局部优化、全局恶化
- 审查更全面,发现跨模块问题

---

### 4. Diagnose(调试纪律)→ 调试子流程

> 来源:Matt Pocock `diagnose`,6 阶段系统化调试。

**在测试失败或 Reviewer 否决时触发**(详见 Reviewer 否决权章节的调试子流程)。

**6 阶段**:
1. **建反馈循环**(核心!占 90% 重要性)- 可复现的 pass/fail 信号
2. **复现** - 确认 bug 和用户描述一致
3. **假设** - 3-5 个可证伪假设,排优先级,展示给用户确认
4. **插桩** - 带 `[DEBUG-xxx]` 标签的定向日志(不用"log everything")
5. **修复** - 先写回归测试再修复(如果有合适的测试接缝)
6. **清理 + 复盘** - 删除调试代码、复盘根因、如涉及架构问题触发 improve-codebase-architecture

**关键原则**:
- 不建反馈循环就不猜原因
- 每个假设必须可证伪:"如果 X 是原因,那么改 Y 会让 bug 消失"
- 假设列表展示给用户确认(利用领域知识快速排优先级)
- 调试日志带 `[DEBUG-xxx]` 前缀,清理时一条 grep 搞定

---

### 5. Improve-Codebase-Architecture(架构健康检查)→ 可选 Step 8.5

> 来源:Matt Pocock `improve-codebase-architecture`,定期发现深层耦合。

**在 Step 8 输出阶段后,可选触发架构健康检查:**

**发现候选问题**:
- 理解一个概念需要跳多个小模块 → 可能太浅
- 纯函数只为测试提取,但真实 bug 在调用处 → 缺少 locality
- 模块接口和实现一样复杂 → 浅模块
- 紧耦合泄漏到 seam 之外 → 边界模糊

**删除测试**:想象删除这个模块,如果复杂度消失→它是透传;如果复杂度在调用者中重现→它在发挥价值。

**输出**:
- 编号的深层化机会列表(文件、问题、方案、收益)
- 用 CONTEXT.md 术语命名
- 不重复讨论 ADR 已决定的事项(除非摩擦足够大)

**触发方式**:
- 用户手动触发
- 调试复盘发现架构问题时自动触发
- 每 3 次 auto-coding 后建议触发

---

---

## 使用方法

### A 级(简单任务)
```
帮我写一个 Python 函数,计算两个列表的交集
```
→ 编码(MiMo) → 测试(MiMo) → 验证(MiMo)

### B 级(功能开发)
```
帮我实现一个 REST API,支持用户注册和登录
```
→ 设计(pro) → 编码(MiMo) → 测试(MiMo) → 验证(MiMo)

### C 级(完整项目)
```
从零搭建一个博客系统
```
→ 完整 8 步,全角色参与

---

## 状态持久化

每个项目自动创建 `.auto-coding/state.json`:

```json
{
  "task_id": "ac-a3940ea1",
  "current_phase": "implementation",
  "completed_phases": ["design", "decomposition"],
  "complexity": "B",
  "results": { "code": "..." },
  "veto_count": 1,
  "veto_feedback": "..."
}
```

**作用**:session 中断后重新运行,自动从上次阶段恢复,不用从头来。

---

## 审批策略

每个项目可自定义 `.auto-coding/rules.yaml`:

```yaml
auto_approve:
  edit: ["src/*", "test/*", "*.py"]
  run: ["npm test", "pytest"]

require_approval:
  edit: ["config/*", ".env*"]
  delete: ["*"]
  run: ["git push", "rm -rf"]
```

---

## 快速开始

```python
from auto_coding_workflow import AutoCodingWorkflow

workflow = AutoCodingWorkflow(
    requirements="实现用户登录功能",
    timeout_minutes=30
)
result = await workflow.run()
```

### 增强版(推荐)

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

## 与历史版本的区别

| 特性 | v3.1 | v3.2 | v3.3 | v3.4.1 | v3.5 | v3.6.1 (当前) |
|------|------|------|------|--------|------|---------------|
| Provider | 轻量 | deepseek | xiaomimimo | - | - | - |
| 流程 | 6 阶段 | 6 阶段 | 8 步循环 | 8 步循环 | 8 步循环 | 8 步循环 |
| Reviewer 否决权 | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| 复杂度分级 | 理论 | 理论 | 自动判断 | 自动判断 | 自动判断 | 自动判断 |
| Soul 数量 | 8 | 8 | 8 | 8 | 8 | 8 |
| 模型分配 | 按角色 | 按角色 | 按阶段 | 按阶段 | **按阶段真实切换** | **MiMo 优先** |
| 状态持久化 | 理论 | 理论 | 实际支持 | 实际支持 | 实际支持 | 实际支持 |
| 审批策略 | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| 自动推进 | ❌ | ❌ | ❌ | ❌ | **✅ 不中途停下** | ✅ |
| 分步输出 | ❌ | ❌ | ❌ | ❌ | **✅ 每步输出** | ✅ |
| 全子代理 | ❌ | ❌ | ❌ | ❌ | ❌ | **✅** |
| 阶段日志可追溯 | ❌ | ❌ | ❌ | ❌ | ❌ | **✅** |
| Heartbeat 巡检 | ❌ | ❌ | per-task cron | per-task cron | per-task cron | **统一扫描** |
| grill-with-docs | ❌ | ❌ | ❌ | **✅** | ✅ | ✅ |
| tdd | ❌ | ❌ | ❌ | **✅** | ✅ | ✅ |
| zoom-out | ❌ | ❌ | ❌ | **✅** | ✅ | ✅ |
| diagnose | ❌ | ❌ | ❌ | **✅** | ✅ | ✅ |
| improve-architecture | ❌ | ❌ | ❌ | **✅** | ✅ | ✅ |

---

## 状态恢复机制(v3.6.1)

采用 Heartbeat 统一巡检模型(替代旧的 per-task Cron):
- **Worker 写标记**:running 标记每 5 分钟更新一次 `last_reported`(避免同一状态重复汇报)
- **Heartbeat 扫一次**:每 30 分钟扫一次所有标记,汇总汇报
- **终态自动清理**:done/failed 汇报后立刻清理标记,不留垃圾

旧 Cron 模式(每任务 5 分钟轮询)已淘汰,只保留兼容性触发条件:

| current_phase | 动作 |
|---------------|------|
| `completed` | 飞书通知完成报告 → 删 cron |
| `failed` | 飞书通知失败报告 → 删 cron |
| `rejected` | 飞书通知终止报告 → 删 cron |
| `timeout` | 飞书通知超时报告 → 删 cron |
| `approval_required` | 飞书通知审批 → 继续轮询 |

```bash
# 查看所有 cron
openclaw cron list

# 手动删 cron
openclaw cron rm ac-monitor-ac-xxxx
```

---

*Updated: 2026-05-21 | Auto-Coding v3.6.1*
