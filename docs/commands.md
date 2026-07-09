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

```bash
python main.py --generate-organizational-metrics
```

Optional overrides:

```bash
python main.py --generate-organizational-metrics --metrics-repo owner/repo --metrics-output-dir <output-dir>
```
