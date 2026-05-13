# PII Cleanup Checklist

**Date**: 2026-05-13
**Goal**: Remove all hardcoded personal info, instance names, and sensitive IDs before GitHub push

## 🔴 Must Fix — ✅ ALL DONE

- [x] 1. `__init__.py:21,25` — author email removed
- [x] 2. `README.md:5` — author email removed
- [x] 3. `README-FULL.md:5` — author email removed
- [x] 4. `PROJECT.md:4` — 负责人: 虾软 → removed
- [x] 5. `PROJECT.md:266` — 维护者: 虾软 → "Auto-Coding Project"
- [x] 6. `auto_coding_workflow.py:490` — hardcoded 飞书 open_id → env var `AUTO_CODING_FEISHU_TO`
- [x] 7. `agent_soul_loader.py:229-230` — hardcoded 虾软/虾总 paths → generic paths

## 🟡 Recommended — ✅ ALL DONE

- [x] 8. `auto_coding_workflow.py:1162-1189` — model mappings now support env var override `AUTO_CODING_MODEL_<ROLE>`
- [x] 9. `workers/reviewer_worker.py:53` — added comment clarifying model is not used directly
- [x] 10. `workers/base_worker.py:370` — DummyWorker test code, left as-is (acceptable)
- [x] 11-12. Fallback models → configurable via `AUTO_CODING_FALLBACK_MODELS` env var
- [x] 13. `workflow_config.py` — historical doc, left as-is
- [x] 14. "老板指定" comments → removed
- [x] 15. `.gitignore` — added `.auto-coding/`
- [x] 16. Version number alignment (README, README-FULL, __init__.py all v3.4.1)

## Environment Variables Added

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_CODING_FEISHU_TO` | (empty) | 飞书通知目标 open_id |
| `AUTO_CODING_MODEL_<ROLE>` | (varies) | 按角色覆盖模型，如 `AUTO_CODING_MODEL_OPTIMIZER=provider/model` |
| `AUTO_CODING_FALLBACK_MODELS` | `xiaomimimo/mimo-v2.5,xiaomimimo/mimo-v2.5-pro` | Fallback 模型列表 |
