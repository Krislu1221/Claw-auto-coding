# Auto-Coding v3.6.1 — 完整文档

**版本**: v3.6.1
**更新日期**: 2026-05-21

---

## 📖 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [核心架构](#核心架构)
4. [模型分配](#模型分配)
5. [内嵌 Agent Soul](#内嵌-agent-soul)
6. [使用指南](#使用指南)
7. [配置说明](#配置说明)
8. [文件清单](#文件清单)
9. [故障排除](#故障排除)
10. [更新日志](#更新日志)

---

## 概述

### 什么是 Auto-Coding？

**Auto-Coding** 是一个智能自主编码系统，通过多角色 Soul + 多模型切换，完成从需求到代码的完整开发流程。

**核心理念**: 不是任务分发器，而是自我完善的智能编程系统。它利用不同角色的专业视角和不同模型的风格互补，进行设计→分解→编码→测试→反思→优化→验证→输出，实现多维度的自我审查和自我优化，提升代码可执行率。

**v3.3 关键变更**:
- ✅ **内嵌 8 个 Agent Soul**：不再依赖外部 `agency-agents` 目录，编码专用 Soul 内置
- ✅ **双模型驱动**：MiMo v2.5 Pro + DeepSeek v4 Pro
- ✅ **按阶段分配模型**：设计/编码/审查/测试/优化/验证各用不同模型
- ✅ **状态持久化**：项目级 `.auto-coding/state.json`，session 断了可恢复
- ✅ **审批策略**：项目级 `.auto-coding/rules.yaml`，敏感操作自动拦截
- ✅ **Cron 监控**：任务启动后自动创建 cron job，每 5 分钟轮询状态，终态自动飞书通知

### 适用场景

✅ **推荐使用**:
- 复杂项目开发（多任务依赖）
- 技术方案设计和实现
- 代码审查和优化
- RoundTable 研讨后的编码实现

❌ **不推荐**:
- 简单单文件修改（直接让主 Agent 写更快）
- 需要立即回答的问题
- Token 预算有限的场景

---

## 快速开始

### 1. 环境要求

- OpenClaw 2026.5.7+
- `xiaomimimo` + `deepseek` provider 已配置
- `openclaw` CLI 可用

```bash
# 验证
openclaw --version
openclaw infer model run --model xiaomimimo/mimo-v2.5-pro --prompt "hello" --json --local
```

### 2. 基本使用

```python
import asyncio
from auto_coding_workflow import AutoCodingWorkflow

async def main():
    workflow = AutoCodingWorkflow(
        requirements="写一个计算两个列表交集的 Python 函数，要求有类型注解和文档字符串",
        timeout_minutes=10
    )
    result = await workflow.run()
    print(result)

asyncio.run(main())
```

### 3. 增强版工作流（推荐）

```python
from workflow_enhanced import AutoCodingWorkflowEnhanced

workflow = AutoCodingWorkflowEnhanced(
    requirements="实现用户登录功能",
    project_dir="./my-project",   # 必须：用于存储配置和状态
    resume=True,                  # 自动恢复未完成的任务
)
await workflow.run()
```

第一次运行会自动生成：
- `.auto-coding/workflow.yaml.template` → 复制为 `workflow.yaml` 自定义流程
- `.auto-coding/rules.yaml.template` → 复制为 `rules.yaml` 自定义审批规则

---

## 核心架构

### 本质

**单进程串行 + 多角色 Soul + 多模型切换**

不是真正的多 Agent 并行 spawn（并发风险高），而是同一个 Python 进程串行执行，每一步换不同的模型和 Soul prompt，换不同的人格和视角来审视代码。

### 八步循环

```
设计(Design) → 分解(Decomposition) → 编码(Coding) → 测试(Testing)
    ↑____________________________________________________↓
                         反思(Reflection) → 优化(Optimization)
                                                 ↓
验证(Verification) → 输出(Output)
```

**迭代逻辑**: 测试→反思→优化 形成迭代循环（最多 3 次），测试通过后跳出。

### 模型调用链

Python 脚本无法直接 import `openclaw.tools`，改用 CLI 调用：

```
openclaw infer model run
    --model xiaomimimo/mimo-v2.5-pro
    --prompt "[SYSTEM]\n{system_prompt}\n\n[USER]\n{task_prompt}"
    --json
    --local
```

解析 JSON 返回的 `outputs[0].text`，拿到真实代码。

---

## 模型分配

### 按阶段分配（v3.4.1）

| 阶段 | Soul 角色 | 说明 |
|------|----------|------|
| 设计/分解 | software-architect | 综合最强，架构权衡、方案对比 |
| 编码 | senior-developer | 代码专用，类型注解规范 |
| 审查 | code-reviewer | 逻辑推理独特优势 |
| 前端编码 | frontend-developer | 代码专用 |
| 后端架构 | backend-architect | 综合最强 |
| 测试 | api-tester | 全面严谨 |
| 优化 | **optimizer** | **最优雅实现** |
| 验证 | **verifier** | **严谨全面** |

### 关键原则

- **auto-coding 要质量不要速度**：优先选择能力最强的模型
- **模型可通过环境变量覆盖**：`AUTO_CODING_MODEL_<ROLE>=provider/model`
- **Fallback 可配置**：`AUTO_CODING_FALLBACK_MODELS=provider/model1,provider/model2`

---

## 内嵌 Agent Soul

v3.4 起，8 个编码专用 Soul 直接内嵌在 `agent_soul_loader.py` 中，**不再依赖外部目录**。

| Agent ID | 名称 | 专长 |
|----------|------|------|
| `engineering-software-architect` | 软件架构师 | 架构设计、DDD、系统思维 |
| `engineering-backend-architect` | 后端架构师 | 分布式系统、数据库、API 设计 |
| `engineering-senior-developer` | 高级开发工程师 | Python 实现、类型注解、性能优化 |
| `engineering-frontend-developer` | 前端工程师 | React/Vue、组件设计、性能 |
| `engineering-code-reviewer` | 代码审查专家 | PR 审查、安全、最佳实践 |
| `testing-api-tester` | API 测试工程师 | 接口测试、边界条件、幂等性 |
| `engineering-optimizer` | **代码优化工程师** | 优雅重构、性能最优 |
| `testing-verifier` | **交付验证工程师** | 功能完整性、边界覆盖 |

如需扩展 Soul，可通过 `agency_path` 参数指定外部目录作为补充。

---

## 使用指南

### A 级快速通道（单函数 / 小 Bug）

直接用 `AutoCodingWorkflow`，不走完整八步：

```python
workflow = AutoCodingWorkflow(
    requirements="写一个斐波那契数列函数",
    timeout_minutes=2
)
result = await workflow.run()
```

### B 级中等任务（新功能模块）

预定义任务列表：

```python
tasks = [
    {'id': 1, 'name': '设计数据库模型', 'depends_on': []},
    {'id': 2, 'name': '实现 CRUD API', 'depends_on': [1]},
    {'id': 3, 'name': '编写单元测试', 'depends_on': [2]},
]

workflow = AutoCodingWorkflow(
    requirements="实现用户管理模块",
    tasks=tasks,
    timeout_minutes=30
)
result = await workflow.run()
```

### C 级复杂项目（完整系统）

使用增强版工作流：

```python
workflow = AutoCodingWorkflowEnhanced(
    requirements="开发一个完整的电商后台管理系统",
    project_dir="./ecommerce-admin",
    resume=True,
)
result = await workflow.run()
```

---

## 配置说明

### 项目级配置（`.auto-coding/workflow.yaml`）

```yaml
phases:
  - name: design
    agent: engineering-software-architect
    model: xiaomimimo/mimo-v2.5-pro
    enabled: true
  - name: implementation
    agent: engineering-senior-developer
    model: xiaomimimo/mimo-v2.5-pro
    enabled: true
  - name: review
    agent: engineering-code-reviewer
    model: xiaomimimo/deepseek/deepseek-v4-pro
    enabled: true
  - name: optimization
    agent: engineering-optimizer
    model: xiaomimimo/DeepSeek v4 Pro
    enabled: true
  - name: verification
    agent: testing-verifier
    model: xiaomimimo/DeepSeek v4 Pro
    enabled: true
```

### 审批规则（`.auto-coding/rules.yaml`）

```yaml
auto_approve_edit:
  - "src/*"
  - "test/*"
  - "*.py"
  - "*.js"
  - "*.md"

require_approval_edit:
  - "config/*"
  - ".env*"
  - "*.config.js"

require_approval_delete:
  - "*"  # 删除任何文件都需要审批

notify_on_complete: true
```

### 状态文件（`.auto-coding/state.json`）

```json
{
  "version": "1.0",
  "task_id": "ac-xxxx",
  "requirements": "...",
  "current_phase": "implementation",
  "completed_phases": ["design", "decomposition"],
  "results": { ... },
  "approval_queue": []
}
```

---

## 文件清单

| 文件 | 行数 | 说明 |
|------|------|------|
| `auto_coding_workflow.py` | ~950 | 主工作流（八步循环） |
| `workflow_enhanced.py` | ~650 | 增强版工作流（状态+审批+通知） |
| `workers/base_worker.py` | ~300 | Worker 基类（含模型调用） |
| `workers/engineering_worker.py` | ~280 | EngineeringWorker |
| `workers/testing_worker.py` | ~310 | TestingWorker |
| `workers/reviewer_worker.py` | ~250 | ReviewerWorker（否决权） |
| `agent_soul_loader.py` | ~350 | Soul 加载器（内嵌 8 个 Soul） |
| `state_manager.py` | ~260 | 状态持久化 |
| `approval_rules.py` | ~270 | 审批规则引擎 |
| `feishu_notifier.py` | ~240 | 飞书通知 |
| `check_auto_coding_status.py` | ~220 | Cron 监控脚本 |
| `complexity_analyzer.py` | ~200 | 复杂度自动分级（A/B/C） |
| `phase_model_allocator.py` | ~370 | 模型分配 |
| `model_selector.py` | ~300 | 模型选择器 |
| `dependency_manager.py` | ~450 | 依赖管理 |
| `workflow_config.py` | ~200 | 配置加载器 |
| `task_manager.py` | ~150 | 任务管理 |
| `SKILL.md` | ~400 | Skill 入口文档 |
| `PROJECT.md` | ~300 | 项目过程文档 |
| `README-FULL.md` | 本文件 | 完整文档 |

---

## 故障排除

### 模型调用返回空 / 失败

**现象**: `⚠️ 模型调用失败: Error: No text output returned...`

**排查**:
```bash
# 1. 验证 CLI 可用
openclaw infer model run --model xiaomimimo/mimo-v2.5-pro --prompt "hello" --json --local

# 2. 检查模型是否在 models.json 中配置
openclaw models list | grep xiaomimimo

# 3. 检查 API Key 是否有效
# 火山引擎 Coding Plan 需要单独购买，确保额度充足
```

### Soul 加载为 0 个

**现象**: `⚠️ 未找到 agency-agents，使用默认路径`

**解决**: v3.3 已内嵌 8 个 Soul，此警告不影响功能。如需外部 Soul，设置环境变量：
```bash
export AUTO_CODING_AGENCY_PATH=/path/to/agency-agents
```

### 状态恢复失败

**现象**: `resume=True` 但从头开始

**排查**:
- 确认 `project_dir/.auto-coding/state.json` 存在
- 确认 `current_phase` 不是 `completed`/`failed`/`rejected`

---

## 更新日志

### v3.3 (2026-05-09)
- **新增**: 项目级配置 (`workflow.yaml`)、审批规则 (`rules.yaml`)
- **新增**: 状态持久化 (`state.json`)，支持断点续传
- **新增**: Cron 自动监控 + 飞书通知
- **新增**: 2 个 Soul（optimizer、verifier），共 8 个内嵌 Soul
- **新增**: 按阶段模型分配（设计/编码/审查/测试/优化/验证各用不同模型）
- **修复**: 模型调用链改用 `openclaw infer model run --json --local`
- **修复**: Soul 内嵌化，不再依赖外部 `agency-agents` 目录
- **修复**: Fallback 模型改为 `xiaomimimo/MiMo v2.5 Pro`

### v3.2 (2026-04-27)
- **迁移**: 全量迁移到 `xiaomimimo` provider
- **测试**: 8 个模型全量测试（速度 3s ~ 106s）
- **分配**: Coordinator→doubao-pro, Engineering→doubao-code, Reviewer→deepseek, Testing→doubao-lite
- **修复**: ReviewerWorker 过度批评问题（新增审查边界约束）

### v3.1 (2026-04-20)
- **设计**: 多 Agent 协作架构（Coordinator/Engineering/Review/Testing）
- **约束**: 发现子 Agent 跨 provider 限制

### v2.0 (2026-03-25)
- **融合**: Auto-Coding + Karpathy 编码铁律
- **铁律**: 思考优先、极简主义、手术刀修改、目标导向

### v1.1.0 (2026-03-20)
- **增强**: 上下文管理、依赖管理、超时保护

### v1.0.0 (2026-03-19)
- **初版**: 八步循环工作流

---

*Last updated: 2026-05-09 | Auto-Coding v3.3*
