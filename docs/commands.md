## Label Synchronization

Synchronize required workflow labels to the target repository:

```bash
python main.py --sync-labels
```

## Target Repository Initialization

Create baseline instruction files in `CIRCUS_TARGET_REPO_PATH` without overwriting existing files:

```bash
python main.py --init
```

## Organizational Metrics (Read-Only)

Generate lightweight organizational metrics from local Watchtower artifacts without mutating GitHub state or workflow labels:

- Seeded categories:
  - run outcomes (`success`, `exit_code`, `outcome`, `mode`, `state_label`)
  - blocker categories (stop reasons, dependency diagnostics, lifecycle/traceability decision diagnostics)
  - recovery events (decision, reason, non-destructive flag, dependency status)
  - review churn (review result contracts and review-to-developer cycle counts)
  - implementation-plan churn (planner outcomes, generated issue counts, stale-check status)
  - planning-to-implementation traceability (recommendation and accepted-decision traceability signals)
- These metrics are review and visibility inputs only; they do not dispatch work, change labels, choose models, or act as workflow control signals.

```bash
python main.py --generate-organizational-metrics
```

Optional overrides:

```bash
python main.py --generate-organizational-metrics --metrics-repo owner/repo --metrics-output-dir <output-dir>
```
