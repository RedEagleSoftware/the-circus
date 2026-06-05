# Capability Tree

Systems Architect stewardship: capability-tree planning and sequencing are owned as a strategic function by the Systems Architect role.

## Current Frontier

```mermaid
flowchart LR
    foundation["✓ Workflow Foundation"]
    selfhost["◐ Self Hosting"]
    routing["○ Provider Routing"]
    skills["○ Skills"]

    foundation --> selfhost
    selfhost --> routing
    routing --> skills
```

## Workflow Foundation

```mermaid
flowchart LR
    routing["✓ Issue Routing"]
    dev["✓ Developer Flow"]
    review["✓ Review Flow"]
    archreview["✓ Architect Review"]

    routing --> dev
    dev --> review
    review --> archreview
```

## Self Hosting

```mermaid
flowchart LR
    workspace["○ Workspace Isolation"]
    polling["○ Durable Polling"]
    onboarding["◐ Repository Onboarding"]

    workspace --> polling
    onboarding --> polling
```

## Agent Evolution

```mermaid
flowchart LR
    providers["○ Provider Routing"]
    skills["○ Skills"]

    providers --> skills
```
