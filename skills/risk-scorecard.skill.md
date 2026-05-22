---
name: risk-scorecard
description: "Risk Scorecard 五元组——纪律→借口→信号→阈值→动作，覆盖编码、测试、审查、通用四个分类共12条规则"
type: global
version: "1.0.0"
inject_once: true
---

# Risk Scorecard 五元组

## Overview

Risk Scorecard 是 v3.7-discipline 的第一层和第二层防线。它在每个阶段的前/中/后三个时间点检测纪律违规：
- **阶段开始前（Pre-Mortem）**：Agent 对照 rationalizations 自问「我有没有在找借口」
- **阶段执行中（In-Flight）**：关键操作后检测 signal 是否触发 threshold
- **阶段结束时（Post-Mortem）**：聚合所有检测结果，输出 Scorecard Report

## 五元组字段定义

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `discipline` | string | 要遵守的纪律/原则 | "不跳过测试" |
| `rationalization` | string[] | 常见的偷懒借口（反借口表） | ["太简单不需要测试", "后面补"] |
| `signal` | string | 可观测的信号名（机器可读） | `testing_phase_executed` |
| `threshold` | string | 触发动作的阈值条件（表达式） | `testing_phase_executed == false` |
| `action` | enum | 触发后的动作：block / warn / log | `block` |
| `level` | enum | 严重级别：🔴 阻塞 / 🟡 警告 / 💭 记录 | `🔴` |
| `counter` | string | 对借口的反驳理由（一条总结） | "简单逻辑也有边界情况" |

## 动作级别

| 级别 | 动作 | 行为 | 示例场景 |
|------|------|------|---------|
| 🔴 | block | **立即暂停**，通知主会话，阶段不能继续 | 未跑测试就提交、修改文件数超限 |
| 🟡 | warn | **记录警告**，继续执行但报告标注 | 测试非 RED→GREEN、添加额外抽象 |
| 💭 | log | **静默记录**，仅用于统计分析和阈值校准 | 小规模风格偏离、非关键步骤跳过 |

## 分类与规则（11 条）

### 编码纪律（coding_discipline，5 条）

#### 1. 不跳过测试
- **常见借口**：「太简单不需要测试」「测试可以后面补」「我一眼就能看出对错」
- **信号**：`testing_phase_executed`
- **阈值**：`testing_phase_executed == false`
- **动作**：🔴 block
- **反驳**：简单逻辑也有边界情况；后面补 = 永远不补；人眼验证不可靠

#### 2. 不添加未被要求的功能（YAGNI）
- **常见借口**：「顺便加个配置项，万一要用」「这个抽象以后会省时间」「多写个工具函数没坏处」
- **信号**：`extra_features_added`
- **阈值**：`extra_features_added > 0`
- **动作**：🟡 warn
- **反驳**：你现在不需要它；每次添加都是未来的维护债；需求没说的不要做

#### 3. 手术刀式修改
- **常见借口**：「既然改这个文件，顺便重构一下」「代码风格不统一，一并改了」「就顺手格式化」
- **信号**：`modified_file_count`
- **阈值**：`modified_file_count > 5`
- **动作**：🔴 block
- **反驳**：每次顺手都是引入 bug 的机会；重构是独立任务不是编码时的搭车行为

#### 4. 代码必须有测试覆盖
- **常见借口**：「单元测试没用，集成测试才重要」「覆盖率数字没意义」
- **信号**：`new_code_lines_without_test`
- **阈值**：`new_code_lines_without_test > 200`
- **动作**：🔴 block
- **反驳**：没有单元测试的代码 = 没有安全网的杂技；200 行无测试是明确的危险信号

#### 5. 不制造过度抽象
- **常见借口**：「提取个接口以后方便扩展」「加个策略模式代码更优雅」
- **信号**：`abstraction_layers_added`
- **阈值**：`abstraction_layers_added > 1`
- **动作**：🟡 warn
- **反驳**：一个实现不需要接口；等第二个实现出现时再抽象（Rule of Three）

### 测试纪律（testing_discipline，2 条）

#### 6. 测试必须先失败再通过（RED→GREEN）
- **常见借口**：「我相信测试会通过，不用先跑」「RED 阶段浪费时间」
- **信号**：`test_was_red_before_green`
- **阈值**：`test_was_red_before_green == false 且 非首个测试`
- **动作**：🟡 warn
- **反驳**：没见过 RED 的测试可能测错了东西；RED→GREEN 是 TDD 的核心循环

#### 7. 不测试实现细节
- **常见借口**：「mock 内部方法更方便」「得验证这个 private 方法被调用了」
- **信号**：`test_touches_private_api`
- **阈值**：`test_touches_private_api == true`
- **动作**：🔴 block
- **反驳**：测试只验证 public API；测实现细节的测试在重构时全废

### 审查纪律（review_discipline，3 条）

#### 8. 审查前先 zoom-out
- **常见借口**：「这段代码我熟，不用看上下文」「就看 diff 够了」
- **信号**：`zoom_out_executed`
- **阈值**：`zoom_out_executed == false 且 modified_file_count > 3`
- **动作**：🟡 warn
- **反驳**：不理解的代码不能有效审查；多文件改动必须理解全局

#### 9. 审查覆盖安全
- **常见借口**：「安全问题后面再说」「这个输入肯定是安全的」
- **信号**：`security_checks_passed`
- **阈值**：`security_checks_passed == false`
- **动作**：🔴 block
- **反驳**：安全不能后补；任何用户输入都必须验证

#### 10. 不改动需求明确的做法
- **常见借口**：「这个写法不够优雅，改一下」「应该用更好的模式」
- **信号**：`over_critique_detected`
- **阈值**：`over_critique_detected == true`
- **动作**：🟡 warn
- **反驳**：审查边界：需求明确要求的做法优先于极简主义

### 通用纪律（general_discipline，2 条）

#### 11. 不提交未验证的代码
- **常见借口**：「改了才 3 行，不用跑测试」「之前都通过的，这次肯定没问题」
- **信号**：`tests_passed_after_change`
- **阈值**：`tests_passed_after_change == false`
- **动作**：🔴 block
- **反驳**：3 行也能引入 bug；测试的存在就是为了每次验证

#### 12. 调试前先建反馈循环
- **常见借口**：「我大概知道问题在哪，直接改」「打日志太慢了」
- **信号**：`feedback_loop_established`
- **阈值**：`feedback_loop_established == false 且 debug_attempts > 0`
- **动作**：🔴 block
- **反驳**：不建循环就猜 = 瞎蒙；可复现的 bug > 猜测的 bug

## Scorecard Report JSON 格式

每个阶段结束后输出以下格式的报告：

```json
{
  "phase": "coding",
  "timestamp": "2026-05-22T12:00:00Z",
  "checks": [
    {
      "discipline": "不跳过测试",
      "triggered": false,
      "signal_value": true,
      "threshold": "testing_phase_executed == false",
      "action": "block",
      "level": "🔴",
      "verdict": "pass"
    },
    {
      "discipline": "手术刀式修改",
      "triggered": true,
      "signal_value": 7,
      "threshold": "modified_file_count > 5",
      "action": "block",
      "level": "🔴",
      "verdict": "🔴 触发阻塞: 修改了 7 个文件, 超过阈值 5"
    }
  ],
  "summary": {
    "total": 5,
    "blocked": 1,
    "warned": 0,
    "passed": 4,
    "blocking": true
  }
}
```

**字段说明**：
- `triggered`：boolean，阈值是否被触发
- `signal_value`：当前信号的实际值（类型与信号定义一致）
- `verdict`：`"pass"` 或带详细描述的失败信息（包含 level emoji + 原因 + 数据）
- `summary.blocking`：true 表示有 🔴 block 被触发，阶段不能继续
- 报告写入 `.auto-coding/logs/{order}-{phase}-scorecard.log`

## 执行流程

- **Pre-Mortem（阶段开始前）**：Agent 逐条阅读 rationalizations → 自问「我有没有在想这些借口」→ 匹配则输出 `⚠️ 检测到借口模式: {rationalization} → {counter}` → 明确反驳后再执行
- **In-Flight（阶段执行中）**：关键操作后检测 signal 对比 threshold → 🔴 立即暂停通知主会话 / 🟡 记录警告继续 / 💭 静默记录
- **Post-Mortem（阶段结束时）**：聚合 signal 结果 → 生成 Report JSON → 写入 `.auto-coding/logs/{order}-{phase}-scorecard.log` → 🔴 阻塞则通知主会话

## 公用信号检测规则

以下规则是**跨阶段**通用的检测逻辑，所有技能文件可引用：

| 规则 ID | 信号 | 检测方法 | 适用范围 |
|---------|------|---------|---------|
| SC-001 | `modified_file_count` | `git diff --stat` 统计变更文件数 | 编码、优化 |
| SC-002 | `tests_passed_after_change` | 运行测试套件检查 exit code | 编码、测试、优化、验证 |
| SC-003 | `new_code_lines_without_test` | 新增代码行数 - 新增测试行数 | 编码 |
| SC-004 | `testing_phase_executed` | 检查测试运行记录 | 编码、优化 |
| SC-005 | `feedback_loop_established` | 检查是否复现 bug + 记录复现步骤 | 调试子流程 |
| SC-006 | `abstraction_layers_added` | 统计新增接口/抽象类/基类数 | 编码、优化 |
| SC-007 | `security_checks_passed` | 检查输入验证、参数化查询 | 编码、测试、审查 |
| SC-008 | `zoom_out_executed` | 检查是否生成全局视角分析 | 审查 |
| SC-009 | `test_was_red_before_green` | 检查测试日志 RED→GREEN 序列 | 测试 |
| SC-010 | `test_touches_private_api` | 检查是否调用 `_private`/`__mangled` | 测试 |

**P0**（🔴 block）：SC-001、SC-003、SC-007 | **P1**（🟡 warn）：其余

**实现**：`scorecard_engine.py` 读取 `scorecard.yaml`，在阶段前/中/后执行检测，结果以 Report JSON 写入日志。
