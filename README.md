# The Circus

> Multi-agent orchestration framework for autonomous software development workflows.

## Overview

The Circus is an experimental multi-agent orchestration platform designed to coordinate specialized AI agents across software engineering workflows. The project focuses on enabling autonomous and semi-autonomous collaboration between agents while keeping GitHub and repository documentation as the source of truth.

The long-term vision is to create a system where:

- Specialized agents operate with distinct responsibilities and doctrine.
- Work is coordinated through issues, tasks, and repository state.
- Persistent project knowledge lives in markdown documentation and version control.
- Agents can safely collaborate, learn, and evolve operational behavior over time.
- Human operators retain oversight while minimizing repetitive engineering overhead.

The Circus emphasizes:

- Clear operational boundaries
- Reproducible workflows
- Documentation-driven coordination
- Git-native automation
- Autonomous execution with auditability
- Incremental and observable agent behavior

---

# Core Concepts

## Agent-Based Architecture

Agents are assigned focused responsibilities rather than acting as generalized assistants.

Examples include:

- Planning agents
- Development agents
- Testing agents
- Review agents
- Documentation agents
- Operations agents

Each agent operates from defined doctrine and project context.

---

## Source of Truth Philosophy

The Circus intentionally avoids treating runtime session memory as authoritative.

Instead, persistent project state should live in:

- GitHub issues
- Repository documentation
- Structured markdown files
- Configuration files
- Source control history

This allows:

- Stateless execution
- Easier recovery from context drift
- Better auditability
- Shared visibility between agents
- Reduced dependency on transient LLM context

---

## Operational Doctrine

The project distinguishes between:

- Mutable operational notes
- Stable doctrine
- Read-only governance documents

Some files may eventually become protected or agent read-only to prevent unintended drift in foundational operational behavior.

---

# Goals

## Near-Term Goals

- Establish reliable multi-agent orchestration
- Improve task decomposition
- Build GitHub-integrated workflows
- Standardize agent prompts and operational contracts
- Develop resilient handoff and review patterns
- Improve automated testing and validation flows

## Long-Term Goals

- Persistent agent collaboration systems
- Self-improving operational guidance
- Dynamic role specialization
- Autonomous backlog management
- Large-scale project coordination
- Cross-repository orchestration
- Long-lived organizational memory

---

# Planned Features

- GitHub issue orchestration
- Agent role registry
- Project-specific operational doctrine
- Structured task routing
- Automated review workflows
- Label synchronization
- Execution auditing
- Agent notes and collaboration channels
- Workflow state tracking
- Human approval checkpoints
- Session isolation and replayability

---

# Design Principles

## 1. Documentation First

Operational context should survive sessions.

## 2. Human Oversight

Agents assist and automate, but humans remain in control of governance and approval.

## 3. Incremental Autonomy

Autonomy should increase only where reliability and observability justify it.

## 4. Explicit Responsibility

Every agent should have a clear operational scope.

## 5. Reproducibility

Runs should be understandable, traceable, and recoverable.

---

# Project Status

The Circus is currently in active early-stage architecture and experimentation.

Expect:

- Rapid iteration
- Breaking changes
- Evolving conventions
- Experimental workflows
- Frequent operational refinement

---

# Contributing

Contributions, ideas, and architectural discussions are welcome.

Areas of interest include:

- Multi-agent coordination
- AI orchestration
- Developer tooling
- GitHub automation
- Workflow reliability
- Prompt engineering
- Operational governance
- AI safety and oversight

---

# Development Philosophy

The Circus is being developed with a strong bias toward:

- Practical engineering workflows
- Real-world developer usability
- Transparent operational behavior
- Maintainable automation
- Clear boundaries between experimentation and governance

The system is intended to augment engineering teams, not obscure them.