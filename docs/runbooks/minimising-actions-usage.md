# Minimising GitHub Actions usage

Use this guide when adding workflows, reviewing recurring CI cost, or deciding
whether another run is useful. Consumers own their triggers, checks and budgets.
Keep dependency grouping in [renovate-config](https://github.com/accelerate-toolkit/renovate-config#internal-and-external-groups),
not in a second delivery-tooling preset. Agent-facing instructions are tracked in
[agent-context #11](https://github.com/accelerate-toolkit/agent-context/issues/11).

## Measure before changing

Review a representative week of runs, including dependency updates and releases.
In Actions, open the expensive or frequently repeated workflows and inspect job
and step durations. Use the account's billing/usage report to confirm billed
usage; elapsed workflow time alone does not measure cost. Record run count,
attempt count, trigger, runner type, total job duration and the reason for repeats.
Compare the same workload after a change rather than dispatching demonstration runs.

Read-only inspection with GitHub CLI:

```sh
gh run list --repo OWNER/REPO --limit 100 \
  --json databaseId,workflowName,event,headSha,conclusion,createdAt
gh run view RUN_ID --repo OWNER/REPO --json jobs,attempt,event,headSha
```

Ten parallel two-minute jobs consume twenty job-minutes, even if they finish in
two minutes. Runner rates, billing rounding and storage can change the actual
charge. Standard hosted runners in public repositories are free; larger runners
can be billed even for public repositories. Private repository usage depends on
the owner's plan. Self-hosted machines still have operating costs. Check current
[GitHub billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
instead of assuming every minute has the same price. Cache and artifact storage
also need appropriate retention; retain release evidence required for recovery.

## Reduce unnecessary runs

Validate PRs once per relevant head. Avoid running the same validation on both
all branch pushes and PR events. A common trigger shape is:

```yaml
on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:
```

The main-branch run can still be necessary: it validates the integrated commit
and may gate publication. Do not remove it merely because a PR was green.
Reserve manual dispatch for a specific recovery or verification need. Inspect
logs and reproduce failures locally first; retry failed jobs when supported and
appropriate, rather than rerunning everything. A changed dependency, corrected
failure or demonstrated transient error is a reason to retry; polling progress
is not. Avoid empty commits and forced rebases just to restart checks.

For documentation-only changes, use local link checks and relevant validation.
When introducing path selection, cover workflow files, shared tooling, manifests,
lockfiles and tests as well as application paths. Do not filter an entire required
workflow out: GitHub can leave its required checks pending. Prefer an always-run
required gate that fails on failed or cancelled relevant checks and explicitly
accepts only intentionally unnecessary work. Do not treat all skipped jobs as
success, or use `[skip ci]` as a general cost policy. See
[GitHub's skipped-workflow behaviour](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).

For validation without side effects, cancel superseded PR runs. For example,
in a workflow whose publication jobs cannot run on PR events:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

Different PR refs remain independent; running main-branch work is not cancelled
by this expression. Do not apply blanket cancellation to publication, deployment
or migration jobs. Also note that default concurrency can replace an older
*pending* run even with cancellation disabled; it is not a durable queue for
every release. Review recovery and ordering requirements using
[GitHub's concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

## Make each run useful

Run cheap validation before expensive suites, and keep matrices limited to
supported combinations that expose distinct failures. Parallelism reduces waiting,
not necessarily total compute. Use the smallest suitable runner based on measured
runtime and cost. Combine small related checks when extra runner setup outweighs
the benefit of separate jobs, but preserve permission and release boundaries.

Cache dependency downloads when restoring and saving the cache is cheaper than
fetching them. Include relevant lockfile, OS and toolchain identity in keys; keep
locked installation and integrity verification. Never cache credentials. Reuse
verified build outputs rather than rebuilding them in publication jobs, while
binding artifacts to the expected source commit.

Set explicit `timeout-minutes` for jobs after reviewing normal and cold-cache
durations, leaving headroom for legitimate variance. Do not copy a hosted Renovate
limit into CI jobs with unrelated workloads. Short timeouts that cause repeated
retries can increase total usage. Keep artifact retention long enough for release
verification and recovery, and avoid retaining disposable test output indefinitely.

## Group Renovate updates and let follow-up runs merge

Inherit the shared internal and external dependency groups. Internal grouping
makes related component changes visible together; external grouping reduces PR
and CI fan-out. Larger groups can be harder to diagnose, so split an exceptional
blocked update deliberately rather than duplicating grouping policy in consumers.
Lock-file maintenance, vulnerability handling and other exceptional updates can
produce separate work: two groups do not guarantee two PRs or two CI runs.

With Renovate-managed merging (`platformAutomerge: false`), a creation window
controls when updates are proposed. Once checks pass, a later hosted run can merge
an eligible PR outside that creation window, provided the repository's merge
policy allows it. This does not mean waiting until the next weekly creation
window, nor does it promise an immediate merge. Renovate merges at most one PR
per target branch per run; another PR may need a rebase and fresh checks after
the first merge. See [Renovate automerge](https://docs.renovatebot.com/key-concepts/automerge/)
and [hosted job scheduling](https://docs.renovatebot.com/mend-hosted/job-scheduling/).

Use the installed hosted app for normal discovery and merging. Do not leave a
second self-hosted schedule active for the same repository. Read dashboard/PR
status before requesting a manual run; repeated requests do not make green checks
arrive sooner. Existing tested repositories must retain meaningful merge checks.
Repositories intentionally configured without CI need not add ceremonial jobs
solely for dependency updates. Consumers explicitly own that merge policy.

Hosted Renovate computation runs on Mend infrastructure; Actions jobs triggered
by its PRs run under GitHub Actions usage rules. Mend Community Cloud currently
has a 30-minute job timeout (verified 2026-11-16); this is separate from an Actions
budget or job timeout. Monitor hosted logs and extraction/lockfile duration, leave
headroom, and investigate slow managers before adding retries. Consult
[Mend's current resource tiers](https://docs.mend.io/renovate/latest/mend-renovate-cloud-resource-tiers)
when limits or service expectations matter.

## Workflow review checklist

- [ ] Triggers avoid duplicate validation and have a reason for every schedule or dispatch.
- [ ] Path selection covers shared inputs and leaves required checks conclusive.
- [ ] Concurrency cancels obsolete validation without interrupting side effects.
- [ ] Matrices and runner sizes cover supported needs with measured cost.
- [ ] Caching and artifact reuse save work without weakening integrity or leaking secrets.
- [ ] Timeouts allow normal cold runs; retention supports recovery without excess storage.
- [ ] Retries address a diagnosed failure; no empty commits or dispatches merely to poll.
- [ ] Dependency grouping is inherited centrally, with exceptional updates understood.
- [ ] Release checks still validate the source commit and artifacts being published.
- [ ] Before/after run counts and job durations demonstrate the proposed saving.

## Delivery-tooling workflow review

Reviewed [check.yml](../../.github/workflows/check.yml) at commit
`ffc1d18c18c31a08978ff2968933d3395ef09481` for
[issue #3](https://github.com/accelerate-toolkit/delivery-tooling/issues/3).
These are observations and follow-ups, not claims that optimisations are deployed.

| Area | Current behaviour | Decision / follow-up |
| --- | --- | --- |
| Triggers | PR validation, main push and manual dispatch; no dependency cron | Keep main validation as the release gate; use dispatch only for recovery. |
| Concurrency | Per-ref group, cancellation disabled | Candidate: cancel superseded PR validation using the conditional example above; retain main release protection. |
| Required checks | Full `make setup check` on every run | Keep until a reliable change-selection gate is justified; avoid whole-workflow docs path exclusions. |
| Matrix | One Ubuntu check job | No speculative matrix expansion. |
| Setup | uv caching disabled; npm install and Go lint setup each run | Measure cold setup cost before adding caches; preserve locked installs. |
| Timeout | No explicit per-job limits | Measure normal/cold job durations, then set separate check, plan and publish limits. |
| Release | check → plan → publish; publish gated on a release decision | Preserve source binding and verified artifact handoff; do not collapse permission boundaries to save setup time. |
| Artifacts | Release evidence retained for 90 days | Review recovery needs before shortening; no blanket retention reduction. |

No workflow execution is needed to validate this document. Implement workflow
follow-ups separately with appropriate local linting and normal change validation;
do not claim savings until comparable execution evidence exists.
