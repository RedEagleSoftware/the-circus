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
