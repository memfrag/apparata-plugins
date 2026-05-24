---
name: skill-to-plugin
description: >
  Package an existing local skill (a SKILL.md, optionally with scripts/,
  references/, or assets/) as a plugin in the apparata-plugins marketplace repo,
  following that repo's own "Adding a New Plugin" process: create the plugin
  directory, adapt the frontmatter, register it in marketplace.json, bump the
  version, update README.md, run the validator, then branch, commit, push, open
  a PR, and merge. Use this skill whenever the user wants to publish, package,
  add, ship, or release a skill as a plugin in the apparata-plugins marketplace
  — phrases like "turn this skill into a plugin", "add my skill to apparata",
  "publish this to the marketplace", or "make a plugin from this skill". Trigger
  even if they don't name the repo, as long as the intent is moving a local
  skill into the apparata-plugins marketplace.
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
argument-hint: "[path-to-skill]"
---

# Skill → apparata-plugins plugin

Package a local skill as a plugin in the **apparata-plugins** marketplace repo and ship it to a merged PR.

## The guiding principle: defer to the repo's own conventions

The apparata-plugins repo documents its own process in its **`CLAUDE.md`** (the "Adding a New Plugin" section) and demonstrates it in every existing plugin. **That is the source of truth.** The steps below are a known-good default, but conventions drift — the version-bump rule, the README format, the directory layout. So *read the repo's `CLAUDE.md` first and follow it where it differs from this skill.* When a detail is ambiguous, **mirror the closest existing plugin** rather than inventing a structure. This is what keeps the skill from going stale as the marketplace evolves, and it's how the layout decisions below stay correct.

## Step 0 — Locate the source skill and the marketplace repo

**Source skill:** from `$ARGUMENTS` — a directory containing `SKILL.md`, or a path to a `SKILL.md` directly. If it's not given and isn't obvious from the conversation, ask. Read its frontmatter (`name`, `description`) and note any bundled resources (`scripts/`, `references/`, `assets/`) — they decide the layout in step 3.

**Marketplace repo:** find the local clone of apparata-plugins. Don't assume a fixed path — it lives in different places on different machines. Verify a candidate by checking that `<repo>/.claude-plugin/marketplace.json` exists and its `.name` is `apparata-plugins`. Try, in order:

1. A repo path the user gave (e.g. a second path in `$ARGUMENTS`).
2. `~/Projekt/git/Claude/apparata-plugins` (the usual location).
3. Otherwise, ask the user where their clone is.

Work against the repo with explicit paths (`git -C <repo> …`, absolute paths). The shell's working directory is often *not* the repo, so relying on `cd` is a common way to silently operate on the wrong tree.

## Step 1 — Read the repo's conventions

Read these before touching anything, so you follow current convention rather than memory:

- `<repo>/CLAUDE.md` — the authoritative "Adding a New Plugin" checklist.
- `<repo>/.claude-plugin/marketplace.json` — the registry shape and current version.
- `<repo>/README.md` — the summary-table and detail-section format.
- An existing plugin that resembles the source skill (one with bundled resources if the source has them, e.g. `mac-migration-plugin`; a bare one like `spotify-plugin` if not).

## Step 2 — Decide the plugin name and layout

- **Plugin directory:** `plugins/<skill-name>-plugin/` (the `-plugin` suffix is the convention).
- **Already registered?** If that plugin already exists in `marketplace.json`, this is an *update*, not a new plugin: edit the files in place, don't add a duplicate registry entry, and don't re-bump the version a second time for the same change.
- **Layout — mirror the closest existing plugin:**
  - *No bundled resources* (just a SKILL.md): `plugins/<name>-plugin/skills/SKILL.md` (like `spotify-plugin`).
  - *Has scripts/references/assets*: `plugins/<name>-plugin/skills/<skill-name>/SKILL.md` with the resource dirs alongside it (like `mac-migration-plugin`). Check the chosen exemplar to confirm — the repo's actual layout wins over this description.

## Step 3 — Copy and adapt the skill

Copy `SKILL.md` and any resource directories into the chosen location. Then adapt the **frontmatter** for plugin use — local skills often lack the fields a marketplace plugin needs:

- `name`, `description` — keep them. The description is the triggering text; preserve its "pushy" specificity.
- `user-invocable: true` — add it so the plugin exposes a `/<skill-name>` slash command (every plugin here is invocable this way). Drop only if the skill is genuinely meant to be auto-trigger-only.
- `allowed-tools:` — list the tools the **body actually uses**. Read the instructions and infer honestly: file reads/writes → `Read, Write, Edit`; shell/git/scripts → `Bash`; confirmation prompts → `AskUserQuestion`; web → `WebFetch`. An over-broad list defeats the purpose; a missing tool breaks the skill at runtime.
- `argument-hint:` — add if the skill takes positional input (e.g. `"<path-to-spec.md>"` or `"[output-path]"`).

Leave the body intact. If it references its scripts, make sure the paths still resolve under the new location.

## Step 4 — Register in marketplace.json

Add an entry to the `plugins` array:

```json
{ "name": "<name>-plugin", "source": "./plugins/<name>-plugin", "description": "<concise one-liner>" }
```

The registry `description` is a **concise, functional one-liner** — not the long pushy triggering description from the frontmatter. Condense it, and match the tone/length of the existing entries.

Then **bump `metadata.version`** — per the repo's CLAUDE.md, bump the minor version (e.g. `2.3.0` → `2.4.0`). Confirm the rule in CLAUDE.md in case it has changed.

## Step 5 — Update README.md

Two edits, both keeping **alphabetical order by display name**:

1. A row in the summary table: `| [Display Name](#anchor) | short description |`.
2. A detail section mirroring the existing format:

```markdown
### Display Name

One sentence on what it does.

**Skill:** `/<command> [args]` — what the skill produces

**Prerequisites:** <deps, or None>
```

Match the surrounding entries — read two neighbors and copy their shape.

## Step 6 — Validate

Run the repo's validator and don't proceed until it passes:

```bash
bash <repo>/scripts/validate-marketplace.sh   # run from the repo root
```

It checks that `marketplace.json` is valid, every registered source exists, and no plugin directory is an unregistered orphan. If it fails, fix the cause (a common one: the new plugin dir exists but isn't registered yet, or vice versa).

## Step 7 — Ship it: branch, commit, push, PR, merge

Show the user the diff first (`git -C <repo> diff` and the new files). Then:

1. **Branch.** If on the default branch (`main`), branch first: `git -C <repo> switch -c add-<name>-plugin`.
2. **Commit.** Stage only the relevant files. Match the repo's commit style (check `git -C <repo> log`): an imperative subject like `Add <name> plugin`, a body describing the skill and noting the version bump. **This repo's history has no AI-attribution trailer — omit it.**
3. **Confirm, then push.** Pushing is outward-facing, so pause for the user's OK, then `git -C <repo> push -u origin add-<name>-plugin`.
4. **PR.** `gh pr create -R <owner>/<repo> --base main --head add-<name>-plugin --title … --body …`.
5. **Merge & sync.** `gh pr merge -R <owner>/<repo> <branch> --merge --delete-branch`, then bring local main up to date: `git -C <repo> switch main && git -C <repo> pull --ff-only`.
6. Report the PR URL and merge commit.

## Gotchas (learned the hard way)

- **HTTPS push with no credentials.** If `git push` fails with `could not read Username for 'https://github.com'`, the `origin` remote is HTTPS but this non-interactive shell has no stored credentials. Check `gh auth status`; if it reports the git protocol as **ssh** and `ssh -T git@github.com` authenticates, switch the remote to SSH and retry: `git -C <repo> remote set-url origin git@github.com:<owner>/<repo>.git`. Tell the user you changed the remote — it's a persistent change.
- **Working directory ≠ repo.** Always use `git -C <repo>` and absolute paths; the cwd is frequently elsewhere.
- **Don't clobber.** If a same-named plugin already exists, treat it as an update (step 2), not a fresh add.
- **Secrets.** Never copy secrets or tokens from a skill into the public marketplace — flag them instead.
