# Auto-Coding v3.4.1 项目过程文档

> **项目时间**: 2026-04-27  
> **目标**: 重构多 Agent 编码系统，支持多模型自动切换  
> **交付物**: `SKILL.md` + 本过程文档

---

## 一、项目背景

### 1.1 为什么要做这个

之前的 auto-coding v3.1 设计了一个多 Agent 协作系统：
- Coordinator → MiniMax-M2.5
- EngineeringWorker → qwen3.6-plus
- ReviewerWorker → glm-5
- TestingWorker → MiniMax-M2.5

但这些模型来自不同 provider（minimax-cn、bailian），而 OpenClaw 的子 agent spawn 对 `model` 参数有限制。

### 1.2 核心问题

老板问了一个关键问题：
> "我们现在换了火山模型以后，必须约束在单模型的 auto-coding 吗？因为火山模型好像没办法支持同时连接不同模型"

这个问题需要验证：
1. 子 agent 能 spawn 哪些模型？
2. 多模型协作是否仍然可行？
3. 如果可行，如何重新分配模型？

---

## 二、技术约束验证

### 2.1 配置查看

查看了 OpenClaw 的模型配置文件 `~/.openclaw/agents/main/agent/models.json`，发现配置了多个 provider：
- `minimax` / `minimax-cn` / `minimax-portal` / `minimax-portal-cn`
- `bailian`（通义千问、MiniMax、GLM、Kimi）
- `volcano-ark`
- `volcengine-plan`（火山引擎 Coding Plan）
- `ollama`（本地）

### 2.2 子 Agent 模型连通性测试

**第一轮测试**（跨 provider）：

| 模型 | 结果 |
|------|------|
| `volcano-ark/kimi-k2.6` | ❌ model not allowed |
| `bailian/qwen3.5-plus` | ❌ model not allowed |
| `minimax-cn/MiniMax-M2.5` | ❌ model not allowed |
| `bailian/glm-5` | ❌ model not allowed |
| `volcengine-plan/kimi-k2.6` | ✅ accepted |
| 默认（不指定） | ✅ accepted |

**结论**：子 agent **只能 spawn volcengine-plan provider 的模型**，其他 provider 全部被拒绝。

### 2.3 volcengine-plan 全量模型测试

根据火山引擎 Coding Plan 的可用模型列表，逐个测试：

| 模型 | 实测耗时 | 可用性 |
|------|---------|--------|
| `doubao-seed-2.0-lite` | **3s** | ✅ |
| `doubao-seed-2.0-code` | **4s** | ✅ |
| `minimax-latest` | **4s** | ✅ |
| `deepseek-v3.2` | **4s** | ✅ |
| `doubao-seed-2.0-pro` | **6s** | ✅ |
| `kimi-k2.5` | **62s** | ✅ |
| `glm-5.1` | **106s** | ✅ |
| `kimi-k2.6` | **~60s** | ✅ |

**关键发现**：
- doubao-seed 系列（lite/code/pro）响应极快（3-6s）
- deepseek-v3.2 和 minimax-latest 也很快（4s）
- kimi 和 glm 系列较慢（60-100s+）

---

## 三、模型分类与 Agent 分配

### 3.1 按速度分层

| 层级 | 响应时间 | 模型 | 标签 |
|------|---------|------|------|
| **极速层** | <5s | `doubao-seed-2.0-lite` | 轻量/对话/低延迟 |
| **高速层** | ~5s | `doubao-seed-2.0-code` | 代码专用/高效 |
| **高速层** | ~5s | `minimax-latest` | 通用/均衡/可靠 |
| **高速层** | ~5s | `deepseek-v3.2` | 推理/逻辑/审查 |
| **中速层** | ~6s | `doubao-seed-2.0-pro` | 专业/高质量/全面 |
| **慢速层** | ~60s | `kimi-k2.5` | 智能/深度/慢 |
| **慢速层** | ~100s | `glm-5.1` | 智能/最慢/备用 |
| **默认层** | ~60s | `kimi-k2.6` | 当前默认/稳定 |

### 3.2 按任务类型分类

#### 编码实现类（高频，必须快）
| 优先级 | 模型 | 理由 |
|--------|------|------|
| **P0** | `doubao-seed-2.0-code` | 4s 响应，代码专用 |
| P1 | `doubao-seed-2.0-pro` | 6s 响应，质量更高 |
| P2 | `deepseek-v3.2` | 4s 响应，逻辑强 |

#### 编排协调类（中等频次，需要全面）
| 优先级 | 模型 | 理由 |
|--------|------|------|
| **P0** | `doubao-seed-2.0-pro` | 6s 响应，专业全面 |
| P1 | `kimi-k2.6` | 当前默认，稳定 |
| P2 | `minimax-latest` | 4s 响应，通用均衡 |

#### 代码审查类（低频，可接受慢）
| 优先级 | 模型 | 理由 |
|--------|------|------|
| **P0** | `deepseek-v3.2` | 4s 响应，推理强 |
| P1 | `kimi-k2.5` | 60s 响应，深度审查 |
| P2 | `glm-5.1` | 100s+ 响应，最慢 |

#### 测试验证类（高频，必须快）
| 优先级 | 模型 | 理由 |
|--------|------|------|
| **P0** | `doubao-seed-2.0-lite` | 3s 响应，最快 |
| P1 | `minimax-latest` | 4s 响应，可靠 |
| P2 | `doubao-seed-2.0-code` | 4s 响应，编码模型 |

### 3.3 Agent 分配方案

| Agent | 首选模型 | 备选模型 | 职责 |
|-------|---------|---------|------|
| **Coordinator** | `doubao-seed-2.0-pro` | `kimi-k2.6` | 任务编排、状态管理 |
| **EngineeringWorker** | `doubao-seed-2.0-code` | `deepseek-v3.2` | 代码生成 |
| **ReviewerWorker** | `deepseek-v3.2` | `kimi-k2.5` | 代码审查 |
| **TestingWorker** | `doubao-seed-2.0-lite` | `minimax-latest` | 测试验证 |

**核心策略**：编码和审查都用 4-5s 的高速模型，避免拖慢流程。慢模型只在关键审查时备选。

---

## 四、A 级任务全流程测试

### 4.1 测试任务
写一个 Python 递归阶乘函数，包含输入验证（非负整数检查）。

### 4.2 各阶段耗时

| 阶段 | Agent | 模型 | 耗时 | 输出 |
|------|-------|------|------|------|
| Analyze | Coordinator | `doubao-seed-2.0-pro` | 23s | A 级，明确 Done 标准 |
| Implementation | EngineeringWorker | `doubao-seed-2.0-code` | 29s | 代码实现 |
| Review | ReviewerWorker | `deepseek-v3.2` | 49s | 审查结论 |
| Verification | TestingWorker | `doubao-seed-2.0-lite` | 10s | 测试通过 |

**总耗时**：~111s（约 2 分钟）

### 4.3 EngineeringWorker 输出

```python
def factorial(n):
    if not isinstance(n, int):
        raise TypeError("输入必须为整数")
    if n < 0:
        raise ValueError("输入必须为非负整数")
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)
```

代码干净、极简，完全按需求实现。

### 4.4 测试验证结果

全部通过 ✅：
- `factorial(5) = 120`
- `factorial(0) = 1`
- `factorial(1) = 1`
- `factorial("10")` → TypeError
- `factorial(-3)` → ValueError

---

## 五、关键问题与修复

### 5.1 发现的问题：ReviewerWorker 过度批评

deepseek-v3.2 给出"不通过"结论，但批评的点有问题：

| Reviewer 批评 | 实际情况 |
|--------------|---------|
| "isinstance(n, int) 过于严格" | 需求明确要求的 |
| "应该用迭代而非递归" | 需求明确要求递归 |
| "边界条件可以简化" | 需求明确要求 n=0 或 n=1 |

**根因**：ReviewerWorker 的 Prompt 只给了 Karpathy 极简主义原则，但没有强调"需求的明确要求优先于极简主义"。

### 5.2 修复方案

在 SKILL.md 中新增"ReviewerWorker 审查边界"约束：

> - **需求明确要求的做法优先于极简主义**：如果代码严格按需求实现，即使你认为可以更极简，只要没有过度设计（未请求的功能、抽象层、配置），应判定为通过
> - **不要在需求明确约束上挑刺**：不要在"需求说怎么做"这件事上批评
> - **只审查"实现方式是否符合需求"和"是否有额外内容"**

---

## 六、经验教训

### 6.1 技术层面

1. **子 agent 模型限制**：OpenClaw 的 `sessions_spawn` 只能 spawn 当前 provider 的模型，跨 provider 全部拒绝
2. **速度差异巨大**：同一 provider 下，最快 3s vs 最慢 100s+，差了 30 倍
3. **任务类型匹配模型**：代码专用模型（doubao-seed-2.0-code）确实更适合编码任务
4. **审查模型需要边界约束**：deepseek-v3.2 推理强但容易过度批评，需要明确审查边界

### 6.2 流程层面

1. **先验证约束再设计**：如果一开始不知道子 agent 只能 spawn volcengine-plan 的模型，设计会完全不同
2. **实测比理论重要**：模型速度标签是理论值，实际 spawn 测试才能确认
3. **Prompt 工程是关键**：ReviewerWorker 的审查边界约束如果早加，测试时就不会出现误判

### 6.3 给后续 Agent 的建议

1. **使用本系统前**：先确认当前 provider 下有哪些可用模型
2. **分配模型时**：高频任务用极速/高速层，低频任务可以用中速/慢速层
3. **审查环节**：如果 Reviewer 给出"不通过"，先检查是"真正的问题"还是"过度批评"
4. **A 级任务**：可以直接走 Implementation → Review → Verification，不需要 Coordinator

---

## 七、交付物清单

| 文件 | 路径 | 说明 |
|------|------|------|
| SKILL.md | `skills/auto-coding-v3/SKILL.md` | 主技能文档（v3.2）|
| PROJECT.md | `skills/auto-coding-v3/PROJECT.md` | 本过程文档 |
| 测试代码 | `factorial.py` | A 级任务测试产物 |
| 记忆文件 | `memory/2026-04-27.md` | 当日项目记录 |

---

## 八、参考信息

### 8.1 模型配置位置
```
~/.openclaw/agents/main/agent/models.json
```

### 8.2 子 agent spawn 语法
```bash
sessions_spawn(runtime="subagent", model="volcengine-plan/MODEL_NAME")
```

### 8.3 已验证可用的模型列表
- `volcengine-plan/doubao-seed-2.0-lite`
- `volcengine-plan/doubao-seed-2.0-code`
- `volcengine-plan/doubao-seed-2.0-pro`
- `volcengine-plan/minimax-latest`
- `volcengine-plan/deepseek-v3.2`
- `volcengine-plan/kimi-k2.5`
- `volcengine-plan/kimi-k2.6`
- `volcengine-plan/glm-5.1`

---

*文档生成时间: 2026-04-27 00:27*  
*维护者: Auto-Coding Project*
