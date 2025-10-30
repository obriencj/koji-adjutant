# Cursor Rule Personalities - Quick Reference

This document provides a quick reference for the AI personality system used in the koji-adjutant project.

## Overview

The project uses five specialized cursor rule files (`.mdc` files) that act as expert personalities to guide different aspects of development. Each personality has specific expertise and coordinates with others to ensure cohesive design and implementation.

## The Personalities

### 1. Strategic Planner (`001_strategic_planner.mdc`)

**Role**: High-level project planning, requirements analysis, and roadmap creation

**Focus**:
- Project goals and constraints
- Integration points with koji hub
- Task prioritization and phasing
- Risk assessment

**When to Consult**:
- Starting a new phase or feature
- Facing requirement ambiguities
- Evaluating architecture trade-offs
- Assessing project risks

**Output**: Strategic plans, requirement documents, architecture decisions

**Globs**: `/**/*.md`, `/**/planning/*`, `docs/planning/**`

### 2. Systems Architect (`002_systems_architect.mdc`)

**Role**: Define system architecture, component boundaries, and interfaces

**Focus**:
- Component design (worker daemon, container manager, task handlers)
- Interface definitions between components
- Data flow and state management
- Container lifecycle management patterns

**When to Consult**:
- Designing new components
- Defining interfaces between modules
- Evaluating architecture trade-offs
- Planning integration points

**Output**: Architecture diagrams, interface specifications, design patterns

**Globs**: `/**/*.md`, `/**/architecture/*`, `docs/architecture/**`

### 3. Implementation Lead (`003_implementation_lead.mdc`)

**Role**: Bridge architecture to code, adapt kojid to adjutant requirements

**Focus**:
- Code adaptation strategies (middle-out approach)
- Identifying reusable kojid components
- Defining abstraction layers for podman integration
- Refactoring plans

**When to Consult**:
- Starting implementation of a feature
- Refactoring existing code
- Evaluating code structure options
- Making compatibility decisions

**Output**: Implementation plans, code structure, adaptation strategies

**Globs**: `/**/*.py`, `koji_adjutant/**/*`, `docs/implementation/*`

### 4. Container Engineer (`004_container_engineer.mdc`)

**Role**: Podman-specific expertise, container orchestration

**Focus**:
- Podman Python API usage patterns
- Container image selection and management
- Volume mounting strategies for build artifacts
- Security considerations (privileges, isolation)

**When to Consult**:
- Designing container architecture
- Implementing podman integration
- Configuring security settings
- Optimizing performance

**Output**: Container configurations, podman integration code, image specifications

**Globs**: `/**/container/*.py`, `/**/*podman*`, `koji_adjutant/container/**`

### 5. Quality Engineer (`005_quality_engineer.mdc`)

**Role**: Testing, validation, integration with koji-boxed environment

**Focus**:
- Test strategies (unit, integration, system)
- Compatibility with existing koji hub
- Performance benchmarking
- Error handling and recovery

**When to Consult**:
- Writing new features
- Fixing bugs
- Ensuring compatibility
- Setting quality standards

**Output**: Test plans, test code, validation criteria

**Globs**: `tests/**/*`, `/**/*test*.py`, `docs/testing/*`

## How They Work Together

### Coordination Workflow

1. **Strategic Planner** creates high-level roadmap and requirements
2. **Systems Architect** defines component boundaries and interfaces
3. **Implementation Lead** creates adaptation plan from kojid to adjutant
4. **Container Engineer** designs podman integration layer
5. **Quality Engineer** defines validation approach

### Collaboration Patterns

- **Planning → Architecture**: Strategic requirements inform architectural design
- **Architecture → Implementation**: Interface specs guide code structure
- **Implementation → Containers**: Code needs drive container integration
- **Containers → Quality**: Container behavior must be validated
- **Quality → Planning**: Test results inform planning decisions

### Parallel Work

Multiple personalities can work simultaneously:
- Strategic Planner defining next phase while Implementation Lead executes current phase
- Container Engineer designing integration while Quality Engineer writes tests
- Systems Architect refining interfaces while Implementation Lead implements

## Using the Personalities

### When Starting Work

1. Identify which personality(ies) are relevant
2. Ask questions in their domain
3. Review their output expectations
4. Follow their guidance
5. Coordinate with other personalities as needed

### Example Interactions

**"How should we structure the container abstraction?"**
→ **Systems Architect** provides interface design
→ **Container Engineer** provides podman implementation details
→ **Implementation Lead** provides code structure

**"What tests do we need for hub compatibility?"**
→ **Quality Engineer** defines test strategy
→ **Strategic Planner** confirms requirements
→ **Systems Architect** verifies compatibility points

**"Should we support custom container images per task?"**
→ **Strategic Planner** evaluates requirements
→ **Container Engineer** assesses feasibility
→ **Systems Architect** designs interface
→ **Implementation Lead** plans implementation

## Key Principles

1. **Specialization**: Each personality focuses on their expertise
2. **Coordination**: Personalities work together, not in isolation
3. **Consistency**: All personalities reference the same project context
4. **Compatibility**: All work maintains hub compatibility as primary constraint
5. **Iteration**: Personalities refine and improve their guidance over time

## File Locations

All personality rule files are in `.cursor/rules/`:
- `.cursor/rules/001_strategic_planner.mdc`
- `.cursor/rules/002_systems_architect.mdc`
- `.cursor/rules/003_implementation_lead.mdc`
- `.cursor/rules/004_container_engineer.mdc`
- `.cursor/rules/005_quality_engineer.mdc`

## Additional Resources

- **Root Rules**: `.cursorrules` - Overall project context and guidelines
- **Bootstrap Session**: `docs/planning/bootstrap_session.md` - Initial coordination plan
- **README**: `README.md` - Project overview

## Getting Started

To begin using the personalities:

1. Read this document to understand the system
2. Review the bootstrap session (`docs/planning/bootstrap_session.md`)
3. Consult the relevant personality when starting work
4. Follow coordination protocols for multi-personality work
5. Document decisions and rationale

The personalities are designed to help you make informed decisions and maintain consistency across the project while leveraging specialized expertise in each domain.
