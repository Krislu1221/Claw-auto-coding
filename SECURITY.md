# Auto-Coding 智能编码系统 — 安全说明

**v3.7.8 安全架构说明**
*最后更新: 2026-05-24*

---

## 🔒 安全设计原则

Auto-Coding 是一个**本地运行的子代理编排系统**。所有子 agent 通过 OpenClaw Gateway 的 `sessions_spawn` 机制创建，在 `isolated` 上下文中执行。不向外部第三方服务发送代码或项目数据。

---

## 🛡️ 安全防护清单

### 子代理隔离
- **实现**: `auto_coding_workflow.py` 中 spawn 使用 `--session isolated` 模式
- **效果**: 子 agent 不继承父 session 的完整上下文，降低信息泄露面
- **超时控制**: 所有子 agent 有 `runTimeoutSeconds` 限制，防止无限挂起

### 模型路由安全
- **实现**: `model_auto_router.py` — 三层决策路由（阶段→分类→上下文阈值）
- **约束**: 仅使用 `volcengine-plan` provider 的模型，跨 provider 调用全部拒绝
- **分工**: Pro 模型做推理/审查，Flash 模型做代码生成/测试

### 表达式求值
- **实现**: `scorecard_engine.py` 中的 `_safe_bool_eval()` — 使用 `ast.parse` 白名单节点
- **策略**: 不支持 `eval()` / `exec()`，仅允许布尔比较表达式（Eq/NotEq/Lt/Gt/And/Or/Not）

### Shell 命令执行
- **子 agent 执行**: cron 监控 agent 白名单为 `exec,message`，在 isolated session 中运行
- **subprocess 调用**: 仅用于调用 `openclaw` CLI（cron add/rm、infer model run），输入均来自本地可控变量
- **风险边界**: 不会将用户原始输入直接拼入 shell 命令

### 飞书通知
- **实现**: `feishu_notifier.py`
- **数据**: 仅发送任务状态摘要（完成/失败/超时）和审批请求
- **凭证**: 飞书 Token 通过 `os.environ` 读取，不硬编码

### 文件系统访问
- **范围**: 仅限 `self.project_dir` 指定的项目目录
- **权限**: 子 agent 继承父进程文件权限，不扩大

---

## 📂 依赖审查

| 依赖 | 用途 | 风险 |
|------|------|------|
| `subprocess` | 调用 openclaw CLI | 中 — 仅调用已知 CLI 命令，输入可控 |
| `asyncio` | 异步编排 | 低 — Python 标准库 |
| `json`, `re`, `os`, `pathlib` | 工具 | 低 — Python 标准库 |
| `httpx` (optional) | HTTP 客户端 | 低 — 仅用于 GitHub API |
| `ast` | 安全表达式求值 | 低 — 白名单节点 |
| `yaml` | 配置文件解析 | 低 — 仅读取 configs/ 下的固定文件 |

本 skill **不依赖**任何第三方数据外传服务。仅与 OpenClaw Gateway（本地）交互。

---

## ⚙️ 安全配置

### 可选环境变量

| 变量 | 文件 | 用途 | 示例 |
|------|------|------|------|
| `AUTO_CODING_FEISHU_TO` | `auto_coding_workflow.py:493` | 接收飞书通知的用户 ID | `ou_xxx` |
| `AUTO_CODING_MODELS` | `model_selector.py:82` | 手动指定模型列表 | `"model1:tag1;model2:tag2"` |
| `AUTO_CODING_MODEL_{ROLE}` | `auto_coding_workflow.py:1196` | 按角色指定模型 | `AUTO_CODING_MODEL_COORDINATOR=doubao-pro` |
| `AUTO_CODING_FALLBACK_MODELS` | `auto_coding_workflow.py:1029` | 降级模型列表 | 逗号分隔的模型名 |

- 所有环境变量均为**可选**配置
- 默认从 gateway config 自动加载模型
- 模型 Provider 约束在 `model_auto_router.py` 中（仅 volcengine-plan）

---

## 🚨 应急响应

如遇到安全问题：

1. **停止所有子 agent**
   ```bash
   openclaw gateway stop
   ```

2. **清理任务目录**
   ```bash
   rm -rf /tmp/auto-coding-*
   ```

3. **检查日志**
   ```bash
   tail -n 200 ~/.openclaw/logs/gateway.log
   ```

4. **更新到最新版本**
   ```bash
   clawhub update auto-coding-correctversion
   ```

---

*版本: v3.7.8 — 安全说明与代码实现一一对应*
