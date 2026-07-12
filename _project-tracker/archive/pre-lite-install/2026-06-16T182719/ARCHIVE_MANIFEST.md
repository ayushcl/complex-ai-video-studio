Install timestamp: 2026-06-16T182719
LPML version: 0.2.0
Governance classification: LIGHTLY_MANAGED
Installer mode: first-install

Actions:
| Original path | Action | New/archive path | Reason | Notes |
|---|---|---|---|---|
| local-project-management-lite/payload/AGENTS.md | installed | AGENTS.md | Codex entrypoint absent | No existing entrypoint overwritten. |
| local-project-management-lite/payload/CLAUDE.md | installed | CLAUDE.md | Claude entrypoint absent | No existing entrypoint overwritten. |
| local-project-management-lite/payload/_project-tracker/ | installed | _project-tracker/ | LPML tracker absent | CURRENT_STATE.md generated from project baseline. |
| local-project-management-lite/payload/.agents/skills/ | merged | .agents/skills/ | Existing .agents/ folder preserved | Only missing LPML skill files copied. |
| local-project-management-lite/payload/.claude/skills/ | merged | .claude/skills/ | Existing .claude/ folder preserved | Existing .claude/settings.local.json and .claude/launch.json left unchanged. |
| README.md | skipped | README.md | Host project README is do-not-touch | Not modified. |
| .env | skipped | .env | Host local environment file is do-not-touch | Not modified. |

Manual review items:
| Path | Reason | User decision |
|---|---|---|
| None | No destructive/ambiguous action was required. | N/A |

Skipped items:
| Path | Reason |
|---|---|
| README.md | Host project documentation, never archived/replaced/modified by LPML. |
| .env | Host local environment file. |
| local-project-management-lite/ | Staging folder remains separate until user confirms removal. |
| .claude/settings.local.json | Existing host tool configuration preserved. |
| .claude/launch.json | Existing host tool configuration preserved. |
| source/script/test/run/media/PDF files | Product/source content, outside LPML install surface. |
