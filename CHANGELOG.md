# Auto-Coding 更新日志

---

## v3.4.1 (2026-05-13)

### 🛡️  新增 1：统一模型降级机制（ClawHub 发布必备）

**问题根因（猫王审查发现）：**
- `model_selector.py` 设计了 4 层降级链路，但 Worker 层完全绕过，直接硬编码
- `workflow_config.py` 的 `DEFAULT_WORKFLOW` 绑定了特定 provider
- 发布到 GitHub/ClawHub 后，其他用户没有 volcengine-plan 直接崩溃

**修复内容（3 个文件）：**

**1. `workers/base_worker.py`**
- 移除 `DEFAULT_MODEL` 硬编码常量
- 新增 `ROLE` 类属性（子类声明：`engineering/testing/reviewer`）
- `__init__` 必须传入 `model_selector`，禁止内部自创建
- 支持 `model_override` 参数（优先级最高，来自 workflow phase 配置）
- 模型选择失败抛出清晰错误信息，而非静默使用硬编码

**2. `workers/engineering_worker.py` + `testing_worker.py`**
- 移除所有 `DEFAULT_MODEL` 硬编码
- 只声明 `ROLE`，模型完全由 ModelSelector 提供
- `_default_config()` 返回 `model=None`，由 BaseWorker 注入

**3. `workflow_config.py`**
- `PhaseConfig` 新增 `role` 字段，`model` 改为 `Optional[str]`
- `DEFAULT_WORKFLOW` 所有阶段移除硬编码模型，只声明 role
- `WorkflowConfigLoader.__init__` 接受 `model_selector` 参数
- 新增 `_resolve_models()` 方法：加载配置后自动为 `model=None` 的阶段动态分配
- 分配失败直接抛出错误，不静默继续

**4. `workflow_enhanced.py`**
- 初始化顺序调整：先创建 `model_selector`，再传给 `WorkflowConfigLoader`
- 所有 Worker 初始化时传入 `model_selector=self.model_selector, model_override=phase.model`
- 删除所有 `worker.config.model = xxx` 手动设置行

**核心原则：**
> **发布给公众使用的 skill 不能假设任何特定 provider 存在。**
> 模型选择必须完全由 ModelSelector 驱动，Worker 只消费 selector 的结果，不做任何自己的 fallback 判断。

---

### 🛡️  新增 2：三重防错自检机制（消灭静默失败）

**问题根因**：之前的错误不是能力问题，是流程缺防错机制

**三道防线（全部 ✅ 验证通过）**：

**1. 契约一致性自检（初始化时自动跑）**
- 位置：`_validate_phase_contract()`
- 作用：验证 `workflow_config` 的每个阶段 ID 必须有对应的 `_phase_xxx` 实现方法
- 不通过直接抛异常（❌ 失败：配置有但实现缺失；⚠️ 警告：实现了但配置不用）
- 开销：<1ms，纯 Python

**2. 变更影响分析（编码阶段前置）**
- 位置：`_phase_coding()` prompt 最前面
- 作用：编码前必须先输出：修改内容是什么？可能影响哪些关联点（阶段ID/字符串/配置/方法名）？需要同步修改的地方有哪些？
- 机制：用 2 秒的前置思考，换避免 30-60 秒的返工循环

**3. 结构审查前置（Reviewer 第一优先级）**
- 位置：`_phase_reflection()` prompt 最前面
- 作用：Reviewer 必须先审查「契约一致性 + 影响范围」，通过了才能看「代码质量」
- 违反顺序直接否决：发现不一致/漏改就是 🔴 阻塞项
- 升级：从「只看代码质量」→「结构优先+质量第二」

**总额外开销**：~5 秒，**0 个新增步骤**（全部嵌入现有流程）

---

### 🐛 Bug 修复：全面审查 & 阶段 ID 修复

**问题发现（猫王审查）**：
- `workflow_enhanced.py` 阶段 ID 与 `workflow_config.py` 不匹配，导致 6/7 阶段被跳过
- 版本号不一致（v3.3 vs v3.4 混合标注）
- `_detect_modified_files` 占位实现无实际检测逻辑

**修复内容**：
1. **阶段 ID 对齐（🔴 严重）**：
   - `_run_phase` 方法映射从 `analyze/research/synthesis/implementation/review` 改为 `design/decomposition/coding/testing/reflection`
   - 方法重命名：`_phase_implementation` → `_phase_coding`、`_phase_review` → `_phase_reflection`
   - 新增 `_phase_testing` 方法（TDD 红-绿-重构）
   - 删除不再使用的 `_phase_synthesis` 方法
   - Reviewer 否决回退逻辑从 `implementation` 改为 `coding`

2. **版本统一**：
   - 所有文件版本号统一为 `v3.4.1`
   - 启动消息、文档字符串同步更新

3. **文件检测增强**：
   - `_detect_files_to_edit`：扩展关键词匹配（测试/数据库/前端等）
   - `_detect_modified_files`：基于状态追踪 + 当前阶段输出去重

4. **语法验证**：
   - 所有核心文件 `py_compile` 检查通过
   - Worker 导入路径验证通过

---

## v3.4 (2026-05-11)

### 核心变更：5 项嵌入式工程技能

基于 Matt Pocock "Skills for Real Engineers" (70k+ stars) 的工程实践，深度嵌入到 8 步流程中。

**1. grill-with-docs → 嵌入 Step 1 设计阶段**
- 设计阶段从“直接出方案”改为“结构化追问”
- 逐个问题走完决策树，每个问题给推荐答案
- 自动维护 `CONTEXT.md` 领域术语表，解决 agent verbose 问题
- 谨慎创建 ADR（三条件全满足才创建）

**2. tdd → 嵌入 Step 4 测试阶段**
- 测试阶段改为严格的红-绿-重构循环
- 垂直切片：禁止“先写所有测试再写代码”
- 测试行为不测实现（public API only）
- 每个循环有检查清单

**3. zoom-out → 嵌入 Step 5 反思阶段**
- 反思阶段先 zoom-out（全局视角）再审查
- 审查 agent 先解释代码在系统中的位置，再审查具体实现
- 减少局部优化、全局恶化

**4. diagnose → 调试子流程**
- 测试失败或 Reviewer 否决时触发 6 阶段调试流程
- 核心：先建反馈循环再猜测
- 3-5 个可证伪假设排优先级
- 带 `[DEBUG-xxx]` 标签的定向日志
- 先写回归测试再修复

**5. improve-codebase-architecture → 可选 Step 8.5**
- 输出阶段后可选触发架构健康检查
- 发现深层耦合、浅模块、边界模糊
- 删除测试验证模块价值
- 每 3 次 auto-coding 后建议触发

### 版本号变更
- v3.3 → v3.4
- SKILL.md description 更新
- 版本对比表新增 5 个嵌入技能列

### 独立 Skills（同时创建）
- `grill-me` — 精简版需求追问
- `caveman` — 极简通信模式
- `to-prd` — 对话→PRD
- `to-issues` — PRD→Issue 拆解
- `triage` — Issue 分诊
- `prototype` — 快速原型

---

## v3.3.2 (2026-05-09 16:12)

- **新增**: Fallback 模型机制 — 火山额度用完自动切 `xiaomimimo/mimo-v2.5`
- `_call_agent` 抽取为 `_call_model`（单次调用）+ `_call_agent`（含 fallback）
- `model_selector.py` FALLBACK_MODEL 更新为 `xiaomimimo/mimo-v2.5`

---

## v3.3.1 (2026-05-09 15:50)

- **修复**: `workflow_enhanced.py` 集成 ReviewerWorker — `_phase_review` 调用 `ReviewerWorker.parse_review_output()`，检测否决并保存 veto 反馈
- **修复**: `workflow_enhanced.py` 集成 ComplexityAnalyzer — `_analyze_complexity` 调用 `analyze_complexity()` 替换内联启发式
- **修复**: `workflow_enhanced.py` 主循环改为 while 循环，支持 Reviewer 否决回退到 implementation
- **修复**: `__init__.py` 新增 `ReviewerWorker`、`ComplexityAnalyzer` 导出
- **修复**: Worker 文件注释更新为 v3.3 模型
- **修复**: README 文件清单移除 coordinator，新增 reviewer_worker.py

---

## v3.3.0 (2026-05-09)

### 核心变更

**1. 模型调用链修复**
- Python 脚本无法 import `openclaw.tools`，改用 `openclaw infer model run --json --local` 直接调用火山引擎 API
- 不再返回 `def main(): pass` 占位符，真正生成代码

**2. 8 个内嵌 Agent Soul**
- 新增 `optimizer`（代码优化工程师）和 `verifier`（交付验证工程师）
- 不再依赖外部 `agency-agents` 目录
- 按阶段分配不同 Soul：设计/编码/审查/测试/优化/验证各有人格

**3. 按阶段模型分配**

| 阶段 | 模型 | 理由 |
|------|------|------|
| 设计/分解 | `doubao-seed-2.0-pro` | 综合最强 |
| 编码 | `doubao-seed-2.0-code` | 代码专用 |
| 审查 | `deepseek-v3.2` | 逻辑推理 |
| 测试 | `doubao-seed-2.0-pro` | 全面严谨 |
| 优化 | `glm-5.1` | 最优雅实现 |
| 验证 | `glm-5.1` | 严谨全面 |

**4. 状态持久化**
- `.auto-coding/state.json`：断点续传，session 断了可恢复

**5. 审批策略**
- `.auto-coding/rules.yaml`：敏感操作自动拦截

**6. Cron 监控**
- 自动创建 cron job，每 5 分钟轮询
- 终态（完成/失败/超时）自动飞书通知

### 清理的旧文件
- `auto_coding_workflow_v3.py`（v3.0 旧版工作流）
- `CHANGELOG-v1.1.0.md`（v1 旧日志）
- `DEPLOYMENT.md`（旧部署说明）
- `PACKAGE-MANIFEST.md`（v1.1 打包清单）
- `P0_P1_FIX_REPORT.md`（旧修复报告）
- `SECURITY-AUDIT.md`（旧安全审计）
- `coordinator/` 目录（遗留模块，主流程不再使用）
- `phase_model_allocator.py`（coordinator 依赖，已无用）

### 配置修复
- `workflow_config.py`：默认模型更新为 v3.3 阶段分配（pro/code/deepseek/glm-5.1）
- `prompts/coordinator.md`：版本 v2.0 → v3.3，更新模型和阶段说明
- `prompts/worker_engineering.md`：版本 v2.0 → v3.3，更新模型和 Karpathy 铁律
- `__init__.py`：新增 `AutoCodingWorkflowEnhanced`、`ReviewerWorker`、`ComplexityAnalyzer` 导出
- `workers/engineering_worker.py`：注释更新为 `doubao-seed-2.0-code`
- `workers/testing_worker.py`：注释更新为 `doubao-seed-2.0-pro`
- `README-FULL.md`：文件清单移除 `coordinator/`，新增 `reviewer_worker.py`

---

## v3.2 (2026-04-27)

- 全量迁移到 `volcengine-plan` provider
- 8 个模型全量测试（速度 3s ~ 106s）
- ReviewerWorker 过度批评修复

## v3.1 (2026-04-20)

- 多 Agent 协作架构设计

## v2.0 (2026-03-25)

- 融合 Karpathy 编码铁律

## v1.1.0 (2026-03-20)

- 上下文管理 + 依赖管理

## v1.0.0 (2026-03-19)

- 初版八步循环

---

*Last updated: 2026-05-13*
