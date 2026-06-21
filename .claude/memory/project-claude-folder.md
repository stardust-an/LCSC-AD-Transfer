---
name: project-claude-folder
description: 每个项目使用 .claude/ 文件夹存放 CLAUDE.md 和 MEMORY.md，每轮检查维护
metadata:
  type: feedback
---

用户希望在每个项目下创建 `.claude/` 文件夹存放 MEMORY.md 等配置文件，便于 git 同步给团队。

**结构：**
- `项目/CLAUDE.md` — 项目级指令和约定（根目录，Claude Code 标准发现路径，自动加载）
- `项目/.claude/MEMORY.md` — 项目记忆索引
- `项目/.claude/memory/` — 具体记忆文件

**Why:** 方便 git 同步给团队，所有记忆配置集中在一个目录。CLAUDE.md 放根目录是因为这是 Claude Code 的标准发现路径。

**How to apply:** 
- 每个项目首次对话时检查是否存在 `CLAUDE.md` 和 `.claude/` 目录，不存在则创建
- 每轮对话判断是否需要更新 CLAUDE.md 或 MEMORY.md
- 项目根目录的 CLAUDE.md 首次创建时参考用户级 `~/.claude/CLAUDE.md`
