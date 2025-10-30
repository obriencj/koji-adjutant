# Koji-Adjutant Bootstrap Planning Session

This document initiates the coordination between cursor rule personalities to bootstrap the koji-adjutant project planning and development.

## Session Overview

**Date**: Initial bootstrap session
**Goal**: Establish initial project plan and coordinate personalities to start development
**Participants**: All 5 cursor rule personalities

## Context Summary

### Project Goal
Create koji-adjutant: a fork of kojid that uses podman containers instead of mock chroots for build execution, while maintaining full compatibility with the koji hub.

### Key Constraints
- Must maintain hub API compatibility
- One ephemeral container per task (similar to mock isolation)
- Integration with existing koji-boxed environment
- Middle-out adaptation strategy

### Reference Materials
- Initial kojid copy: `/home/siege/koji-adjutant/koji_adjutant/kojid.py`
- Koji-boxed: `/home/siege/koji-boxed/`
- Koji: `/home/siege/koji`
- Original source: `/home/siege/koji/builder/kojid`

## Coordination Plan

### Phase 1: Strategic Planning

**Strategic Planner** leads:

**Tasks**:
1. Define project requirements
2. Create phased roadmap
3. Identify key risks
4. Establish success criteria

**Key Questions**:
- What are the minimum viable features for each phase?
- What are the critical hub compatibility requirements?
- What are the major risks and mitigation strategies?
- What defines success at each milestone?

**Deliverables**:
- Requirements document
- Phased roadmap
- Risk assessment
- Success criteria

**Timeline**: Initial planning session

### Phase 2: Architecture Design

**Systems Architect** leads:

**Tasks**:
1. Design container abstraction interface
2. Define component boundaries
3. Specify interfaces between components
4. Document architecture decisions

**Key Questions**:
- What is the ContainerManager interface?
- How do task handlers interact with containers?
- What is the container lifecycle model?
- How do we integrate with koji-boxed?

**Deliverables**:
- Architecture diagrams
- Interface specifications
- Component design documents

**Timeline**: After strategic plan

### Phase 3: Implementation Strategy

**Implementation Lead** leads:

**Tasks**:
1. Create code structure plan
2. Identify kojid code to reuse
3. Define refactoring approach
4. Plan Python 3 migration

**Key Questions**:
- What code from kojid can we preserve?
- How should we structure modules?
- What's the best refactoring sequence?
- How do we handle the Python 3 migration?

**Deliverables**:
- Implementation plan
- Code structure design
- Refactoring strategy
- Migration plan

**Timeline**: After architecture design

### Phase 4: Container Design

**Container Engineer** leads:

**Tasks**:
1. Design podman integration
2. Define container image strategy
3. Plan volume mounting
4. Specify security model

**Key Questions**:
- What container images should we use?
- How should we configure volume mounts?
- What's the security model?
- How do we optimize performance?

**Deliverables**:
- PodmanManager design
- Image selection logic
- Volume mount strategy
- Security configuration

**Timeline**: After implementation strategy

### Phase 5: Testing Strategy

**Quality Engineer** leads:

**Tasks**:
1. Design test strategy
2. Plan compatibility testing
3. Define performance benchmarks
4. Create test infrastructure plan

**Key Questions**:
- What tests ensure hub compatibility?
- How do we validate container integration?
- What's acceptable performance overhead?
- What error scenarios must we handle?

**Deliverables**:
- Test strategy document
- Test coverage plan
- Performance benchmarks
- Quality criteria

**Timeline**: After container design

## First Planning Question

**Strategic Planner** begins coordination with this question:

### Container Strategy Dialogue

Given the decision to use **one ephemeral container per task** (like mock's isolation), we need to establish:

**1. Container Image Selection**:
- How do we determine which container image to use?
- Should we support per-task or per-tag custom images?
- What's the default base image?
- How do we manage image caching and updates?

**2. Task-to-Container Mapping**:
- What container configuration is needed per task type?
- How do we pass task context into containers?
- What environment variables are necessary?
- How do we ensure isolation between tasks?

**3. Volume Management**:
- What directories must be mounted from host?
- How do we handle build artifacts storage?
- What about package caches and repositories?
- How do we ensure proper cleanup?

**Next Steps**:
Strategic Planner works with Systems Architect and Container Engineer to resolve these questions, then presents the decisions back to the group for the next phase.

## Coordination Protocol

### Decision Making
1. Lead personality proposes decision
2. Other personalities review and provide input
3. Consensus reached on approach
4. Decision documented
5. Next personality takes lead

### Information Sharing
- All decisions documented in appropriate subdirectories
- Architecture decisions → `docs/architecture/decisions/`
- Planning decisions → `docs/planning/decisions/`
- Implementation decisions → `docs/implementation/decisions/`

### Iteration
- Start with high-level strategic plan
- Drill down into architecture details
- Refine implementation strategy
- Design container integration
- Establish testing approach
- Iterate as needed

## Expected Outcomes

### Initial Deliverables
1. Strategic plan with phased roadmap
2. Architecture design with interfaces
3. Implementation strategy for code adaptation
4. Container design for podman integration
5. Test strategy for validation

### Subsequent Deliverables
- Begin Phase 1 implementation
- Write first container abstraction code
- Implement basic task execution
- Validate with simple tests
- Iterate on feedback

## Success Criteria

Planning is successful when:
1. All personalities have contributed
2. Initial roadmap is defined
3. Architecture is documented
4. Implementation approach is agreed
5. Container strategy is established
6. Testing approach is defined
7. Team can proceed to implementation

## Notes

- This is a living document - update as plans evolve
- Decisions should be traceable to rationale
- Keep alignment with original kojid behavior
- Maintain compatibility as primary constraint
- Use iterative refinement approach

## Session End

**Next Action**: Strategic Planner initiates the first planning dialogue about container strategy, coordinating with Systems Architect and Container Engineer to establish the foundation for all subsequent work.

**Transition**: Once container strategy is established, proceed to detailed architecture design, then implementation planning, then container design, then testing strategy, and finally to Phase 1 implementation.

---

*This bootstrap session establishes the coordination framework for the entire koji-adjutant project. All subsequent work builds on these foundations.*
