# planning

## Customization

prompts and agent definitions use a three-layer override chain (checked in order, first match wins):
1. Project: `.claude/exec-plan/prompts/` and `.claude/exec-plan/agents/`
2. User: `${CLAUDE_PLUGIN_DATA}/prompts/` and `${CLAUDE_PLUGIN_DATA}/agents/`
3. Bundled defaults (shipped with the plugin)

To customize, place your modified version in the override path. For example, to customize `prompts/review.md` at the project level:
```
.claude/exec-plan/prompts/review.md
```
Or at the user level (applies to all projects). To find `<plugin-id>`, run `ls ~/.claude/plugins/data/` and look for the planning plugin entry:
```
~/.claude/plugins/data/<plugin-id>/prompts/review.md
```
Same pattern works for any prompt or agent file — just mirror the path under the override directory.

Nothing is copied into the override directories automatically.

To start from the bundled version of a file, use the `customize-file.sh` helper, which copies it into place and prints the destination. `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` only expand inside plugin-loaded skill files, so spell both paths out when running this yourself:
```bash
# paths for a marketplace install; adjust if you installed the plugin some other way,
# and confirm the data dir against `ls ~/.claude/plugins/data/`
PLUGIN_ROOT=~/.claude/plugins/marketplaces/agent-kit/plugins/planning
PLUGIN_DATA=~/.claude/plugins/data/planning-agent-kit

# project level, writes .claude/exec-plan/prompts/review.md
bash "$PLUGIN_ROOT/skills/exec/scripts/customize-file.sh" prompts/review.md

# user level, applies to all projects
bash "$PLUGIN_ROOT/skills/exec/scripts/customize-file.sh" prompts/review.md "$PLUGIN_DATA"
```
An override shadows the bundled default permanently and will not pick up changes from later plugin upgrades, so copy only the files you intend to edit. Delete the override to return to the bundled version.

Bundled prompts: `task.md`, `fixer.md`, `review.md`, `codex-review.md`, `finalizer.md`, `stats.md`, `progress-file.md`
Bundled agents: `quality.txt`, `implementation.txt`, `testing.txt`, `simplification.txt`, `documentation.txt`, `smells.txt`
