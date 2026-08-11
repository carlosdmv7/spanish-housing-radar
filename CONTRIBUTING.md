# Contributing

How work gets into this repo. It is a small project with one maintainer, so the
process is deliberately light — but every rule here exists because breaking it
already cost something.

---

## The loop

```bash
# 1. Always branch from a fresh main. Never branch from a branch.
git checkout main && git pull

# 2. Create the branch and switch to it in one step
git checkout -b fix/data-quality-and-ux

# ... do the work ...

# 3. The gate, run on its own. Never piped, never chained behind &&.
make lint
uv run pytest -q

# 4. Commit
git add -A
git commit -m "fix(app): the affordability city filter hid five of the eight cities"

# 5. Publish and open a PR
git push -u origin fix/data-quality-and-ux     # -u only the first time
gh pr create --fill

# 6. Merge once CI is green, then go home
gh pr merge --merge --delete-branch
git checkout main && git pull
```

`git checkout -b` **creates**; `git checkout` alone **switches**. Switching back
to `main` never discards committed work — it just moves you.

---

## Commit messages

Format: `type(scope): what changed, from the reader's point of view`

Subject line in the imperative or present tense, no trailing full stop, ≤72
characters. The body — separated by a blank line — is where the *why* goes, and
where technical detail belongs.

### Types

| Type | Use it when | Real example from this repo |
|---|---|---|
| `feat` | Behaviour the user can see is new | `feat(data): ground prices in what the district actually earns` |
| `fix` | Something was wrong and now is not | `fix(ci): the daily pipeline never had a dbt profile on the runner` |
| `refactor` | The code changed, the behaviour did not | `refactor(app): move load_municipalities into filters` |
| `chore` | Not the code — deps, config, tooling, housekeeping | `chore(deps): bump streamlit to 1.60` |
| `docs` | Documentation, ADRs, README | `docs(adr): give every ADR the alternatives it rejected` |
| `test` | Tests only, no production code | `test(mortgage): cover the rent-and-invest drawdown case` |
| `ci` | Workflows and pipeline plumbing | `ci: stop the screenshot job going red after it succeeds` |

### `refactor` vs `chore` — the line

Both feel like "tidying", so they get confused. The distinction that actually
holds:

> **`refactor` touches code that runs in production and leaves its behaviour
> identical. `chore` touches everything that is not that code.**

Ask: *if I revert this commit, does the running application behave differently?*

- **No, and I edited application code** → `refactor`. Extracting a duplicated
  function, renaming a variable, splitting a 400-line view into components,
  replacing a loop with a comprehension.
- **No, and I did not touch application code** → `chore`. Bumping `uv.lock`,
  adding a `.gitignore` entry, editing `pyproject.toml`, deleting a dead
  scratch file, updating a VSCode setting.
- **Yes** → it is not either of them. It is `feat` or `fix`, whatever you
  intended it to be.

The trap: a dependency bump *can* change behaviour. If bumping dbt changes a
model's output, that commit is a `fix` or a `feat` with the bump in it — not a
`chore`. `chore` is a promise that nothing observable moved.

Rule of thumb: `refactor` is a note to your future self about the code's shape.
`chore` is a note about the repo's plumbing.

### Describe the effect, not the implementation

```
❌ fix(app): add pd.to_datetime conversion in home view
✅ fix(app): last-ingest metric crashed the home page's live snapshot
```

The first can be read off the diff. The second tells you why you should care,
and is the one that surfaces in six months when you search for when the home
page broke.

### Trailers

Commits authored with AI assistance carry:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Branches

```
feat/valencia-barrio-seed
fix/data-quality-and-ux
docs/contributing
```

Same prefix vocabulary as the commit type, `kebab-case`, named for the
intention rather than a ticket number. One branch per PR, one PR per idea. If
the branch name needs a second `and`, it is two branches.

---

## Pull requests

- **Title** follows the same convention as a commit subject.
- **Body** states the problem, the decision, and how it was verified —
  specifically *what was run*, not *what looks right*. Green unit tests are not
  verification on their own in this repo; they have missed real defects before.
- CI must be green before merge. `--merge` (not squash) is the house default:
  the individual commits are the story, so they are worth keeping.
- Delete the branch on merge.

An architectural decision — a change to the grain, the scoring, the warehouse
layout, or where a repair happens in the pipeline — gets an
[ADR](docs/adr/) in the same PR. See
[ADR-0007](docs/adr/0007-repair-location-in-silver-not-extraction.md) for the
shape.

---

## Working from VSCode

Recommended extensions are pinned in
[.vscode/extensions.json](.vscode/extensions.json); VSCode offers to install
them on first open.

| Action | How |
|---|---|
| Source Control panel | `Ctrl+Shift+G` |
| Create / switch branch | Click the branch name, bottom-left in the status bar |
| Stage a file | `+` on hover |
| **Stage individual lines** | Select in the diff → right-click → *Stage Selected Ranges* |
| Commit | Message box → `Ctrl+Enter` |
| Push | Sync icon in the status bar |

*Stage Selected Ranges* is the one worth learning: it splits a messy working
tree into two clean commits without touching the terminal.

**GitLens** (already recommended) annotates each line with its commit.
**GitHub Pull Requests** lets you open and review PRs without leaving the
editor.

---

## Three rules that are not negotiable

**Never commit directly to `main`.** Even a typo. `main` is what is deployed.

**Never pipe the gate.** `ruff check . | tail -3 && git commit` swallows the
exit code — the pipe succeeds, `&&` believes the lint passed, and broken code
lands. Run the check on its own, read the result, then commit.

**One commit is one change explainable in one sentence.** If the message needs
an "and also", split it.

---

## Deploying data changes

`dbt build --select some_model+` **does not include seeds**. If a change touches
`transform/seeds/`, production needs the seed reloaded first or it will silently
serve the old rows while reporting success:

```bash
uv run dbt seed  --project-dir transform --target prod --full-refresh
uv run dbt build --project-dir transform --target prod --full-refresh --select some_model+
```

Then query production and confirm the numbers actually moved. `make deploy-prod`
does the full sequence.
