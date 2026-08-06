# ableton skills

Home for Ableton Live skills. Empty for now — this folder reserves the
namespace and the conventions so new skills land consistently.

## Adding a skill here

Follow [AGENTS.md → Adding a new skill](../../../AGENTS.md#adding-a-new-skill).
In short: `.agents/skills/ableton/<name>/` with a `SKILL.md` (routing
frontmatter + agent instructions), a `README.md` (human-facing), scripts under
`scripts/`, and a discovery symlink in `.claude/skills/`.

Shared Ableton helper code (e.g. an `.als` gzip-XML parser, a User Library
locator) should live once at `.agents/shared/ableton/` and be imported via the
standard `sys.path` stanza — same pattern the rekordbox skills use with
`.agents/shared/rekordbox/`.

## Ideas on deck

- **project-inspector** — read an `.als` (gzipped XML) and report tempo,
  tracks, devices, and referenced samples without opening Live.
- **sample-collector** — find every sample a project references and copy the
  missing ones into the project folder (a scriptable "Collect All and Save").
- **stem-importer** — take stems (e.g. from the `vocals` util) and lay them
  out into a new Live set.
