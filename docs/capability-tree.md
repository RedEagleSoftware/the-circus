## Capability Tree

```mermaid
flowchart LR
    foundation[Workflow Foundation]
    selfhost[Self Hosting]
    polling[Durable Polling]
    repo[Repository Onboarding]
    providers[Provider Routing]
    skills[Skills]

    foundation --> selfhost
    selfhost --> polling
    selfhost --> repo
    polling --> providers
    repo --> providers
    providers --> skills
```