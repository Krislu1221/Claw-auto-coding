# PUBLISH_NOTES — ClawHub 发布脱敏记录

## PII 清理状态 (v3.4.1)

| 类型 | 原始值 | 处理方式 |
|------|--------|----------|
| 作者邮箱 | krislu666@foxmail.com | 改为 `your-email@example.com` |
| 飞书用户 ID | ou_71a4f771e6fb01261ea476b657b4f344 | 改为环境变量 `AUTO_CODING_FEISHU_TO` |
| 实例名 | 虾软/虾总 | 移除，改为通用描述 |
| 硬编码路径 | ~/.enhance-claw/instances/虾软/ | 移除，改为 `project_dir` 参数 |
| 实例负责人 | 虾软 | 改为通用描述 |

## ClawHub 安全合规

- 无主动监控术语（心跳兜底、周期自动检查、自动扫描等）
- `.clawhubignore` 排除 `tests/`、`docs/`、`.auto-coding/`
- SKILL.md 与 README.md 版本号已同步 (v3.4.1)

## 环境变量配置

用户部署时需要配置的环境变量：
- `AUTO_CODING_MODEL_<ROLE>` — 按角色覆盖模型
- `AUTO_CODING_FALLBACK_MODELS` — 逗号分隔的降级模型列表
- `AUTO_CODING_FEISHU_TO` — 飞书通知目标用户 ID
