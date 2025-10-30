# Koji-Adjutant

A fork of the koji build daemon (kojid) that replaces mock chroot-based build environments with podman containers while maintaining full compatibility with the koji hub.

## Project Overview

Koji-adjutant acts as a worker node in a koji build system, receiving tasks from the koji hub and executing them in isolated podman containers rather than mock chroots. This modernization maintains all compatibility with the existing koji infrastructure while leveraging container technology.

## Key Features

- **Full Hub Compatibility**: Maintains API compatibility with koji hub - no hub changes required
- **Podman Integration**: Uses podman containers instead of mock chroots for build isolation
- **Ephemeral Containers**: One isolated container per task (similar to mock's approach)
- **Koji-Boxed Integration**: Designed to work seamlessly with existing koji-boxed environment
- **Middle-Out Adaptation**: Reuses kojid code where possible, adds container abstraction layer

## Project Structure

```
koji-adjutant/
├── .cursor/                      # Cursor IDE configuration
│   └── rules/                    # Personality rule files (AI assistants)
│       ├── 001_strategic_planner.mdc
│       ├── 002_systems_architect.mdc
│       ├── 003_implementation_lead.mdc
│       ├── 004_container_engineer.mdc
│       └── 005_quality_engineer.mdc
├── .cursorrules                  # Root-level project rules
├── docs/                         # Project documentation
│   ├── architecture/             # Architecture documents
│   ├── implementation/           # Implementation plans
│   └── planning/                 # Planning documents
├── koji_adjutant/                # Source code
│   └── kojid.py                  # Original kojid (reference)
├── plan/                         # Original planning directory
└── README.md                     # This file
```

## Development Approach

### Personality-Based Development

This project uses specialized cursor rule files (personalities) to guide different aspects of development:

1. **Strategic Planner** - High-level planning, requirements, and roadmap
2. **Systems Architect** - Component design and interface definitions
3. **Implementation Lead** - Code adaptation strategies and refactoring
4. **Container Engineer** - Podman expertise and container management
5. **Quality Engineer** - Testing strategies and validation

Each personality provides expert guidance in their domain while coordinating with others to ensure cohesive design and implementation.

### Middle-Out Strategy

1. **Define Interfaces**: Create abstraction layers for container management
2. **Adapt Existing**: Refactor kojid code to use new interfaces
3. **Extend New**: Implement podman-specific execution layer

### Container Model

**One ephemeral container per task**:
- Each task spawns a dedicated podman container
- Container lifecycle: create → execute → cleanup
- Full isolation between concurrent tasks
- Containers discarded after task completion

## Reference Architecture

### Koji Components

Koji consists of three main pieces:
1. **koji** - Core library and APIs
2. **kojihub** - Central hub service (manages database, tasks, coordination)
3. **builder/kojid** - Worker daemon (executing tasks - this is what we're forking)

### Key References

- **Original kojid**: `/home/siege/koji-adjutant/koji_adjutant/kojid.py` (working copy)
- **Koji source**: `/home/siege/koji/builder/kojid` (source of truth)
- **Koji-boxed**: `/home/siege/koji-boxed/` (integration environment)
- **Hub service**: `/home/siege/koji-boxed/services/koji-hub/` (coordination service)

## Getting Started

### Prerequisites

- Python 3.11+
- Podman with accessible socket
- Koji source code reference
- Koji-boxed environment (for integration testing)

### Initial Planning

See the bootstrap planning session:
- `docs/planning/bootstrap_session.md` - Initial coordination and planning

### Development Workflow

1. Consult personality rules for guidance in their domain
2. Reference original kojid for behavior
3. Follow middle-out adaptation strategy
4. Maintain compatibility as primary constraint
5. Write tests as you implement

## Project Goals

### Phase 1: Foundation
- Define container abstraction interface
- Create podman integration layer
- Implement basic task execution in container
- Validate with simple tasks

### Phase 2: Core Functionality
- Implement build task handlers
- Container image management
- Volume mounting strategy
- Error handling and cleanup

### Phase 3: Advanced Features
- Chain build support
- Image build tasks
- Repo management tasks
- Performance optimization

### Phase 4: Production Readiness
- Comprehensive testing
- Documentation
- Performance benchmarking
- Integration with koji-boxed

## Key Principles

1. **Compatibility First**: Maintain compatibility with koji hub at all costs
2. **Incremental Adaptation**: Reuse as much kojid code as possible
3. **Clean Abstractions**: Isolate podman-specific code in dedicated modules
4. **Security Conscious**: Follow container security best practices
5. **Observable**: Log everything, make debugging easy
6. **Testable**: Design for unit and integration testing

## Contributing

See the personality rule files in `.cursor/rules/` for expert guidance:
- Planning concerns → Strategic Planner
- Architecture questions → Systems Architect
- Implementation issues → Implementation Lead
- Container problems → Container Engineer
- Testing needs → Quality Engineer

## Success Criteria

The adjutant is successful when:
1. It can execute koji build tasks in containers
2. Hub cannot distinguish it from a mock-based kojid
3. It integrates seamlessly with koji-boxed
4. Performance is comparable to mock-based execution
5. It handles errors gracefully and cleans up resources

## License

(To be determined based on koji upstream license)

## Acknowledgments

Based on the koji build system by Red Hat. Original kojid daemon serves as the foundation for this project.
