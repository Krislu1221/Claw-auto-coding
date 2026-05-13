# Auto-Coding v3.4.1

**版本**: v3.4.1  
**更新日期**: 2026-05-13

---

## 概述

Auto-Coding 是一个智能自主编码系统，通过多角色 Soul + 多模型切换，完成从需求到代码的完整开发流程：

```
设计 → 分解 → 编码 → 测试 → 反思 → 优化 → 验证 → 输出
```

**本质**: 单进程串行 + 多角色 Prompt + 多模型切换。不是真正的多 Agent 并行，而是每一步换不同的人格和模型来审视代码。

**v3.4.1 核心特性**:
- ✅ **内嵌 8 个 Agent Soul** — 编码专用 Soul 内置
- ✅ **多模型切换** — 按阶段自动选择最优模型（环境变量可覆盖）
- ✅ **按阶段分配模型** — 设计/编码/审查/测试/优化/验证各用不同模型
- ✅ **统一模型降级** — Worker 通过 ModelSelector 动态分配，禁止硬编码
- ✅ **三重防错自检** — 契约一致性 + 变更影响分析 + 结构审查前置
- ✅ **状态持久化** — `.auto-coding/state.json`，session 断了可恢复
- ✅ **审批策略** — `.auto-coding/rules.yaml`，敏感操作自动拦截
- ✅ **Cron 监控** — 自动轮询任务状态，终态自动飞书通知
- ✅ **5 项嵌入式工程技能** — grill-with-docs / tdd / zoom-out / diagnose / improve-architecture

---

## 快速开始

### 环境要求

- OpenClaw 2026.5.7+
- 至少一个 LLM provider 已配置

```bash
openclaw --version
openclaw models list
```

### 基本使用

```python
import asyncio
from auto_coding_workflow import AutoCodingWorkflow

async def main():
    wf = AutoCodingWorkflow(
        requirements="写一个计算两个列表交集的 Python 函数",
        timeout_minutes=10
    )
    result = await wf.run()
    print(result)

asyncio.run(main())
```

### 增强版工作流（推荐）

```python
from workflow_enhanced import AutoCodingWorkflowEnhanced

workflow = AutoCodingWorkflowEnhanced(
    requirements="实现用户登录功能",
    project_dir="./my-project",
    resume=True,
)
await workflow.run()
```

第一次运行自动生成配置模板：
- `.auto-coding/workflow.yaml.template` → 复制为 `workflow.yaml`
- `.auto-coding/rules.yaml.template` → 复制为 `rules.yaml`

---

## 模型分配（按阶段）

| 阶段 | Soul 角色 | 模型 | 理由 |
|------|----------|------|------|
| 设计/分解 | software-architect | 综合最强，架构权衡 |
| 编码 | senior-developer | 代码专用，类型注解规范 |
| 审查 | code-reviewer | 逻辑推理独特优势 |
| 前端编码 | frontend-developer | 代码专用 |
| 后端架构 | backend-architect | 综合最强 |
| 测试 | api-tester | 全面严谨 |
| **优化** | **optimizer** | **最优雅实现** |
| **验证** | **verifier** | **严谨全面** |

---

## 内嵌 Agent Soul（8 个）

| Agent ID | 名称 | 专长 |
|----------|------|------|
| `engineering-software-architect` | 软件架构师 | 架构设计、DDD |
| `engineering-backend-architect` | 后端架构师 | 分布式系统、数据库 |
| `engineering-senior-developer` | 高级开发工程师 | Python 实现、类型注解 |
| `engineering-frontend-developer` | 前端工程师 | React/Vue、组件设计 |
| `engineering-code-reviewer` | 代码审查专家 | PR 审查、安全 |
| `testing-api-tester` | API 测试工程师 | 接口测试、边界条件 |
| `engineering-optimizer` | **代码优化工程师** | 优雅重构、性能最优 |
| `testing-verifier` | **交付验证工程师** | 功能完整性、边界覆盖 |

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `auto_coding_workflow.py` | 主工作流（八步循环） |
| `workflow_enhanced.py` | 增强版（状态+审批+通知） |
| `workers/base_worker.py` | Worker 基类（含模型调用） |
| `workers/reviewer_worker.py` | ReviewerWorker（否决权） |
| `workers/engineering_worker.py` | EngineeringWorker |
| `workers/testing_worker.py` | TestingWorker |
| `agent_soul_loader.py` | Soul 加载器（内嵌 8 个 Soul） |
| `state_manager.py` | 状态持久化 |
| `approval_rules.py` | 审批规则引擎 |
| `feishu_notifier.py` | 飞书通知 |
| `check_auto_coding_status.py` | Cron 监控脚本 |
| `SKILL.md` | Skill 入口文档 |
| `README-FULL.md` | 完整文档 |

---

## 故障排除

### 模型调用失败

```bash
# 验证 CLI 可用
openclaw models list

# 检查 provider 配置
openclaw config get providers
```

### Soul 加载警告

v3.4.1 已内嵌 8 个 Soul，外部 `agency-agents` 目录不存在不影响功能。如需扩展：

```bash
export AUTO_CODING_AGENCY_PATH=/path/to/agency-agents
```

---

## 更新日志

| 版本 | 日期 | 关键变更 |
|------|------|---------|
| v3.4.1 | 2026-05-13 | 统一模型降级 + 三重防错自检 + 阶段ID修复 + PII清理 |
| v3.4 | 2026-05-11 | 5项嵌入式工程技能 (grill-with-docs/tdd/zoom-out/diagnose/improve-architecture) |
| v3.3 | 2026-05-09 | 8 个 Soul + 按阶段模型分配 + 状态持久化 + 审批规则 + Cron 监控 |
| v3.2 | 2026-04-27 | 全量迁移 volcengine-plan，8 模型测试，Reviewer 过度批评修复 |
| v3.1 | 2026-04-20 | 多 Agent 架构设计 |
| v2.0 | 2026-03-25 | 融合 Karpathy 编码铁律 |
| v1.1.0 | 2026-03-20 | 上下文管理 + 依赖管理 |
| v1.0.0 | 2026-03-19 | 初版八步循环 |

完整文档见 `README-FULL.md`。

---

*Last updated: 2026-05-13 | Auto-Coding v3.4.1*
