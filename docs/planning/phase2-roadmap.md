# Phase 2 Roadmap: Production Readiness

**Date**: 2025-01-27
**Status**: Planning
**Lead**: Strategic Planner
**Phase 1 Completion**: 2025-10-30

## Executive Summary

Phase 2 transforms koji-adjutant from a functional prototype into a production-ready build worker. Building on Phase 1's solid foundation of container abstraction and basic task execution, Phase 2 focuses on dynamic configuration, hub policy integration, complete buildroot environments, performance optimization, and comprehensive testing.

**Core Mission**: Enable production deployment by implementing hub-driven image selection, real configuration management, complete buildroot setup, and performance validation that matches or exceeds mock-based kojid.

## Phase 2 Goals: What Makes It "Production Ready"

Phase 2 achieves production readiness when:

1. **Hub Policy Integration**: Worker dynamically selects container images based on hub-configured policies per build tag/task type
2. **Real Configuration**: Full kojid.conf parsing replaces hardcoded stubs, enabling flexible worker configuration
3. **Complete Buildroot**: Full RPM build environment matching mock capabilities (dependencies, repos, environment setup)
4. **Performance Parity**: Container-based execution performs comparably to mock-based kojid (< 20% overhead)
5. **Production Testing**: Comprehensive test suite covering edge cases, failure modes, and integration scenarios
6. **Operational Readiness**: Graceful shutdown, resource cleanup, error recovery, and observability

## Priority Features: Ranked with Rationale

### P0: Critical for Production (Must Have)

#### 1. Hub Policy-Driven Image Selection
**Priority**: P0 - Critical
**Rationale**: Production requires different container images per build tag (e.g., `f39-build` vs `el10-build`), architecture, or task type. Current single-image approach is insufficient for real koji deployments.

**Scope**:
- Design hub policy API for image selection rules
- Implement policy evaluation engine
- Support tag-based, arch-based, and task-type-based image selection
- Fallback to default image when policy unavailable
- Cache policy results to reduce hub queries

**Impact**: Enables multi-tag, multi-arch production deployments

#### 2. Real kojid.conf Parsing
**Priority**: P0 - Critical
**Rationale**: Hardcoded config stubs (`adjutant_task_image_default()` functions) prevent operator configuration. Production requires configurable timeouts, registry settings, mount policies, and worker identity.

**Scope**:
- Integrate `koji.read_config_files()` from koji library
- Parse `[adjutant]` section in kojid.conf
- Support all Phase 1 config keys (image defaults, pull policy, mounts, timeouts, network)
- Maintain backward compatibility with Phase 1 defaults
- Validate config on worker startup

**Impact**: Enables operator control without code changes

#### 3. Complete Buildroot Setup
**Priority**: P0 - Critical
**Rationale**: Current simplified `rpmbuild` command lacks dependency resolution, repo configuration, and environment setup required for real RPM builds. Without complete buildroot, builds will fail for packages requiring dependencies.

**Scope**:
- Implement buildroot initialization sequence (deps, repos, env)
- Integrate with koji buildroot API for dependency resolution
- Set up yum/dnf repositories inside container
- Configure build environment variables and macros
- Handle buildroot reuse/caching when appropriate
- Support koji buildroot configuration format

**Impact**: Enables successful builds for complex packages

### P1: High Value (Should Have)

#### 4. exec() Pattern for Step Execution
**Priority**: P1 - High Value
**Rationale**: Current bash -c approach with complex heredocs is hard to debug. exec() pattern provides cleaner config file management, better error attribution, and easier debugging of build steps.

**Scope**:
- Add `exec()` method to ContainerManager for executing commands in running containers
- Add `copy_to()` method for copying files from host to container
- Refactor BuildrootInitializer to return structured data (not bash script)
- Update BuildArchAdapter to use create/copy/exec/remove pattern
- Write config files (yum repos, RPM macros) to proper locations in container

**Impact**: Cleaner architecture, better debugging, easier maintenance

#### 5. Operational Monitoring and Status Server
**Priority**: P1 - High Value
**Rationale**: Production operations require visibility into worker state. Without monitoring, operators cannot see what tasks are running, which containers are active, or debug stuck builds.

**Scope**:
- Minimal HTTP server (bottle/flask) running in background thread
- REST endpoints for worker status, active containers, task details
- Container registry to track active containers with metadata
- Live log streaming endpoint
- Optional: Simple HTML dashboard with auto-refresh

**Impact**: Dramatically improves operational visibility and debugging

#### 6. Performance Benchmarking and Optimization
**Priority**: P1 - High Value
**Rationale**: Need to validate that container overhead is acceptable (< 20% vs mock). Optimization opportunities may exist in image caching, container reuse, or parallel operations.

**Scope**:
- Benchmark container startup vs mock chroot creation
- Measure task execution time (container vs mock) for representative packages
- Profile container lifecycle overhead (create, start, cleanup)
- Optimize image pull/caching strategy
- Optimize container creation when possible
- Document performance characteristics

**Impact**: Validates production viability and identifies optimization opportunities

#### 7. Enhanced Error Handling and Recovery
**Priority**: P1 - High Value
**Rationale**: Production requires robust error recovery, detailed diagnostics, and graceful degradation. Current error handling is basic.

**Scope**:
- Enhanced container error diagnostics (logs, exit codes, resource limits)
- Retry logic for transient failures (network, registry)
- Graceful degradation when policy/hub unavailable
- Worker health checks and self-diagnostics
- Better error messages for operators

**Impact**: Reduces operational burden and improves reliability

#### 8. Comprehensive Testing Suite
**Priority**: P1 - High Value
**Rationale**: Current smoke tests (65% coverage) validate basic functionality but don't cover edge cases, failure modes, or production scenarios.

**Scope**:
- Unit tests for config parsing, policy evaluation, buildroot setup
- Integration tests for hub policy integration
- Failure mode tests (network failures, registry failures, container crashes)
- Performance regression tests
- Multi-tag, multi-arch test scenarios
- Test coverage target: 80%+ (excluding kojid.py reference)

**Impact**: Ensures reliability and prevents regressions

### P2: Nice to Have (Can Defer)

#### 7. Network Policy Implementation
**Priority**: P2 - Deferrable
**Rationale**: Phase 1 always enables network. Some builds may require network isolation for security. Can defer if not immediately needed.

**Scope**:
- Implement `adjutant_network_enabled = false` support
- Container network isolation when disabled
- Policy-driven network enable/disable per task

**Impact**: Enhanced security for air-gapped or restricted builds

#### 8. Container Reuse/Caching Strategy
**Priority**: P2 - Deferrable
**Rationale**: Could optimize performance by reusing containers for similar tasks, but adds complexity. Measure first, optimize if needed.

**Scope**:
- Container reuse for sequential tasks with same image/config
- Warm container pool for common images
- Metrics to validate benefit vs complexity

**Impact**: Potential performance improvement (measure first)

## Hub Policy Design: High-Level Approach

### Policy API Design

**Hub-Driven Policy**: Hub stores image selection policies in tag extra data or global configuration. Worker queries hub for policy applicable to current task.

**Policy Format** (JSON in hub tag extra or config):
```json
{
  "adjutant_image_policy": {
    "rules": [
      {
        "tag": "f39-build",
        "arch": "x86_64",
        "image": "registry/koji-adjutant-task:f39-x86_64"
      },
      {
        "tag": "el10-build",
        "arch": "aarch64",
        "image": "registry/koji-adjutant-task:el10-aarch64"
      },
      {
        "task_type": "buildArch",
        "image": "registry/koji-adjutant-task:build"
      },
      {
        "default": true,
        "image": "registry/koji-adjutant-task:default"
      }
    ]
  }
}
```

**Policy Evaluation**:
1. Query hub for tag extra data (if available)
2. Match rules in order: tag+arch → tag → task_type → default
3. Cache policy results per tag/arch combination (TTL: 5 minutes)
4. Fallback to `adjutant_task_image_default` config if hub unavailable

**Implementation Strategy**:
- Create `PolicyResolver` class in `koji_adjutant/policy.py`
- PolicyResolver queries hub via koji XMLRPC API
- Task adapters call `PolicyResolver.resolve_image(tag, arch, task_type)`
- Caching layer reduces hub query overhead
- Config overrides: `adjutant_policy_enabled = true/false`

**Integration Points**:
- BuildArchAdapter: Resolve image from build tag + arch
- CreaterepoAdapter: Resolve image from repo tag (if applicable)
- Future task adapters: Use same policy resolution

**Error Handling**:
- Hub unavailable: Fallback to config default, log warning
- Policy parse error: Fallback to config default, log error
- Image not found: Surface as BuildError with clear message

## Config Parsing Strategy: kojid.conf Integration

### Current State

Phase 1 uses hardcoded functions in `koji_adjutant/config.py`:
- `adjutant_task_image_default()` → hardcoded `"registry/almalinux:10"`
- `adjutant_image_pull_policy()` → hardcoded `"if-not-present"`
- `adjutant_container_mounts()` → hardcoded `["/mnt/koji:/mnt/koji:rw:Z"]`
- `adjutant_network_enabled()` → hardcoded `True`
- `adjutant_container_timeouts()` → hardcoded `{"pull": 300, "start": 60, "stop_grace": 20}`

### Target State

Replace hardcoded functions with real `kojid.conf` parsing using koji library's `read_config_files()`.

### Implementation Approach

**Step 1: Integrate koji Config Parsing**
- Import `koji.read_config_files()` in `koji_adjutant/config.py`
- Parse config on worker startup (in `kojid.py` main entry point)
- Store parsed config in module-level dict or Config object

**Step 2: Define `[adjutant]` Section**
- Support `[adjutant]` section in kojid.conf
- Parse all Phase 1 config keys:
  ```
  [adjutant]
  task_image_default = registry/koji-adjutant-task:almalinux10
  image_pull_policy = if-not-present
  container_mounts = /mnt/koji:/mnt/koji:rw:Z
  network_enabled = true
  container_timeouts = pull=300,start=60,stop_grace=20
  policy_enabled = true
  policy_cache_ttl = 300
  ```

**Step 3: Backward Compatibility**
- Keep existing function signatures in `config.py`
- Functions read from parsed config dict (with defaults)
- Phase 1 code continues to work without changes

**Step 4: Config Validation**
- Validate on startup: required keys, value formats, ranges
- Log warnings for deprecated/unknown keys
- Fail fast on critical config errors

**Step 5: Environment Overrides**
- Support environment variable overrides (e.g., `KOJI_ADJUTANT_TASK_IMAGE_DEFAULT`)
- Useful for containerized deployments (koji-boxed)

### Config Key Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `task_image_default` | string | `registry/almalinux:10` | Default container image when policy unavailable |
| `image_pull_policy` | string | `if-not-present` | Pull policy: `if-not-present\|always\|never` |
| `container_mounts` | list | `["/mnt/koji:/mnt/koji:rw:Z"]` | Default mounts (space-separated or comma-separated) |
| `network_enabled` | bool | `true` | Enable container network |
| `container_timeouts.pull` | int | `300` | Image pull timeout (seconds) |
| `container_timeouts.start` | int | `60` | Container start timeout (seconds) |
| `container_timeouts.stop_grace` | int | `20` | Graceful stop timeout (seconds) |
| `policy_enabled` | bool | `true` | Enable hub policy-driven image selection |
| `policy_cache_ttl` | int | `300` | Policy cache TTL (seconds) |

## Buildroot Enhancement: Gap Analysis and Implementation Plan

### Current State (Phase 1)

**Simplified Implementation**:
- Basic `rpmbuild` command with `--define "_topdir ..."`
- No dependency resolution
- No repository setup
- No buildroot environment configuration
- No koji buildroot integration

**What Works**:
- Simple SRPM builds with no dependencies
- Basic build directory structure

**What Fails**:
- Packages requiring build dependencies (most real packages)
- Packages needing repo access for sources/dependencies
- Packages requiring specific buildroot configuration

### Target State (Phase 2)

**Complete Buildroot Setup** matching mock capabilities:
- Dependency resolution via koji buildroot API
- Repository configuration (yum/dnf repos) inside container
- Buildroot environment variables and macros
- Koji buildroot configuration format support
- Buildroot reuse/caching when appropriate

### Gap Analysis

| Capability | Phase 1 | Phase 2 Target | Gap |
|------------|---------|----------------|-----|
| Dependency resolution | ❌ None | ✅ Via koji API | High |
| Repository setup | ❌ None | ✅ Yum/dnf repos | High |
| Buildroot config | ❌ None | ✅ Koji format | High |
| Environment vars | ❌ Minimal | ✅ Full set | Medium |
| Build macros | ❌ Basic | ✅ Complete | Medium |
| Buildroot caching | ❌ None | ✅ Optional | Low |

### Implementation Plan

**Step 1: Dependency Resolution**
- Call koji hub API to resolve build dependencies for tag/arch
- Format dependency list for dnf/yum installation
- Handle buildrequires vs requires distinction

**Step 2: Repository Setup**
- Query koji hub for repository URLs for build tag
- Generate `/etc/yum.repos.d/koji.repo` inside container
- Configure dnf/yum to use koji repos
- Handle repo authentication if required

**Step 3: Buildroot Initialization Script**
- Create buildroot setup script (bash) that:
  - Installs build dependencies via dnf
  - Configures environment variables (`BUILDROOT`, `RPM_BUILD_DIR`, etc.)
  - Sets up RPM macros (`%_topdir`, `%_builddir`, etc.)
  - Prepares buildroot directory structure
- Execute script in container before build command

**Step 4: Integration with BuildArchAdapter**
- Replace simplified `rpmbuild` command with:
  1. Buildroot setup script execution
  2. Dependency installation
  3. Actual build command (rpmbuild or koji build helper)
- Maintain Phase 1 fallback for simple builds

**Step 5: Buildroot Caching (Optional)**
- Cache buildroot state for same tag/arch combinations
- Reuse container image layers or volumes
- Measure benefit vs complexity

### Mock Equivalence Checklist

- [ ] Dependency installation matches mock's `--install`
- [ ] Repository configuration matches mock's repo setup
- [ ] Environment variables match mock's chroot environment
- [ ] Build macros match mock's RPM configuration
- [ ] Buildroot directory structure matches mock layout
- [ ] Buildroot reuse matches mock's `--recurse` behavior

## Performance Targets: Benchmarks and Optimization Goals

### Performance Objectives

**Primary Goal**: Container-based execution overhead < 20% vs mock-based kojid

**Secondary Goals**:
- Container startup time < 5 seconds (cold), < 1 second (warm)
- Image pull time < 30 seconds (first time), cached thereafter
- Task execution time parity with mock (±10%)
- Resource cleanup time < 2 seconds per container

### Benchmark Plan

**Test Scenarios**:
1. **Simple Package Build**: SRPM with no dependencies (baseline)
2. **Complex Package Build**: SRPM with 50+ build dependencies
3. **Createrepo Task**: Repository with 1000 packages
4. **Concurrent Tasks**: 5 simultaneous builds

**Metrics to Collect**:
- Container lifecycle: create → start → execute → cleanup (wall clock)
- Image operations: pull time, cache hit rate
- Task execution: build time, createrepo time
- Resource usage: memory, CPU, disk I/O
- Comparison: Mock-based kojid times for same tasks

**Benchmark Methodology**:
- Run each scenario 10 times, report median and p95
- Compare container vs mock for same packages/tasks
- Run on same hardware/environment
- Document hardware specs and environment

### Optimization Opportunities

**Image Operations**:
- Pre-pull common images on worker startup
- Implement image layer caching strategy
- Use image tags with digests for reproducibility

**Container Lifecycle**:
- Optimize container creation (minimize layers, use scratch base)
- Parallel container operations when safe
- Container reuse for sequential same-image tasks (if beneficial)

**Buildroot Setup**:
- Cache dependency lists per tag/arch
- Pre-populate repo configs when possible
- Optimize dnf installation (skip docs, use fast mirror)

**Resource Management**:
- Set appropriate resource limits to prevent resource exhaustion
- Optimize cleanup operations (parallel removal)
- Monitor and tune based on metrics

### Success Criteria

- ✅ Container overhead < 20% for simple builds
- ✅ Container overhead < 30% for complex builds (acceptable due to isolation benefits)
- ✅ Image pull time acceptable (< 30s first time, cached thereafter)
- ✅ No performance regressions vs Phase 1
- ✅ Resource usage comparable to mock-based kojid

## Testing Strategy: Production Confidence

### Current Test Coverage (Phase 1)

- **Coverage**: 65.26% (excluding kojid.py reference)
- **Test Type**: Integration smoke tests (7 tests)
- **Scope**: Basic container lifecycle, task execution, cleanup

### Phase 2 Testing Goals

**Coverage Target**: 80%+ (excluding kojid.py reference)

**Test Categories**:

#### 1. Unit Tests
- **Config Parsing**: Test `kojid.conf` parsing, validation, defaults
- **Policy Resolution**: Test policy evaluation, caching, fallbacks
- **Buildroot Setup**: Test dependency resolution, repo config generation
- **Container Spec Building**: Test spec construction from task context

**Target**: 50+ unit tests

#### 2. Integration Tests
- **Hub Policy Integration**: Test policy query, caching, fallback
- **Config Integration**: Test real `kojid.conf` parsing in worker context
- **Buildroot Integration**: Test complete buildroot setup end-to-end
- **Multi-Tag/Arch**: Test different images per tag/arch
- **Error Scenarios**: Network failures, registry failures, container crashes

**Target**: 20+ integration tests

#### 3. Performance Tests
- **Benchmark Suite**: Measure container vs mock performance
- **Regression Tests**: Ensure no performance degradation
- **Load Tests**: Concurrent task execution, resource limits

**Target**: 10+ performance/benchmark tests

#### 4. Failure Mode Tests
- **Container Failures**: Test cleanup on container crash
- **Network Failures**: Test behavior when registry/hub unavailable
- **Config Errors**: Test validation and error handling
- **Resource Exhaustion**: Test behavior under memory/disk limits

**Target**: 15+ failure mode tests

### Test Infrastructure

**Test Environment**:
- Isolated podman environment for container tests
- Mock koji hub for policy/repo API tests
- Representative test packages (simple, complex, edge cases)

**Test Execution**:
- Unit tests: Fast (< 5 seconds total)
- Integration tests: Moderate (< 2 minutes total)
- Performance tests: Run on-demand (minutes to hours)

**Continuous Integration**:
- Run unit + integration tests on every commit
- Run performance tests on nightly builds
- Generate coverage reports

### Test Coverage Targets

| Component | Current | Phase 2 Target |
|-----------|---------|----------------|
| `config.py` | 0% | 90%+ |
| `policy.py` (new) | N/A | 85%+ |
| `buildroot.py` (new) | N/A | 80%+ |
| `container/podman_manager.py` | 64% | 75%+ |
| `task_adapters/buildarch.py` | 51% | 80%+ |
| `task_adapters/createrepo.py` | 56% | 75%+ |
| **Overall** | **65%** | **80%+** |

## Risk Assessment: Technical and Integration Risks

### High Risk

#### 1. Hub Policy API Design Mismatch
**Risk**: Hub policy format may not align with hub capabilities or koji-boxed setup
**Impact**: Policy integration fails, blocking production deployment
**Mitigation**:
- Prototype policy API with koji-boxed hub early
- Design flexible policy format that can adapt
- Fallback to config-based selection always available

#### 2. Buildroot Complexity Underestimation
**Risk**: Complete buildroot setup more complex than anticipated
**Impact**: Delays Phase 2 completion, may require Phase 3 work
**Mitigation**:
- Start with minimal buildroot (deps + repos), iterate
- Reference mock implementation closely
- Test with real packages early

#### 3. Performance Overhead Exceeds Target
**Risk**: Container overhead > 20% makes adjutant non-viable
**Impact**: May need significant optimization or architectural changes
**Mitigation**:
- Benchmark early (simple packages first)
- Identify bottlenecks early
- Optimize incrementally

### Medium Risk

#### 4. Config Parsing Integration Issues
**Risk**: koji library config parsing may conflict with adjutant needs
**Impact**: Requires custom parsing, increases maintenance
**Mitigation**:
- Test config parsing early with real kojid.conf
- Use koji library patterns where possible
- Document any deviations

#### 5. Multi-Tag/Arch Image Management
**Risk**: Managing multiple images adds operational complexity
**Impact**: Operator burden, potential misconfiguration
**Mitigation**:
- Clear documentation for image requirements
- Validation and error messages
- Image availability checks on startup

#### 6. Koji-Boxed Integration Gaps
**Risk**: Assumptions about koji-boxed may be incorrect
**Impact**: Integration issues discovered late
**Mitigation**:
- Test with koji-boxed environment early
- Coordinate with koji-boxed maintainers
- Document integration requirements

### Low Risk

#### 7. Test Coverage Goals Too Ambitious
**Risk**: 80% coverage may require excessive test maintenance
**Impact**: Slows development, but manageable
**Mitigation**:
- Focus on critical paths first
- Use integration tests where unit tests are difficult
- Accept lower coverage for reference code (kojid.py)

#### 8. Performance Benchmarking Overhead
**Risk**: Benchmarking takes more time than planned
**Impact**: Delays optimization work, but doesn't block functionality
**Mitigation**:
- Start with simple benchmarks
- Automate benchmark execution
- Document methodology for reproducibility

## Success Criteria: How We Know Phase 2 Is Complete

### Functional Success Criteria

- [ ] **Hub Policy Integration**: Worker selects images based on hub policy for multiple tags/arches
- [ ] **Config Parsing**: Worker reads and applies `kojid.conf` settings correctly
- [ ] **Complete Buildroot**: Complex packages with dependencies build successfully
- [ ] **Performance Parity**: Container overhead < 20% for simple builds, < 30% for complex builds
- [ ] **Test Coverage**: 80%+ coverage (excluding kojid.py reference)
- [ ] **Error Handling**: Graceful degradation when hub/registry unavailable
- [ ] **Documentation**: Operator guide, config reference, troubleshooting guide

### Technical Success Criteria

- [ ] **Backward Compatibility**: Phase 1 functionality still works
- [ ] **No Breaking Changes**: Phase 1 interfaces unchanged (additive only)
- [ ] **Performance**: No regressions vs Phase 1
- [ ] **Reliability**: > 99% task success rate in test environment
- [ ] **Observability**: Clear logging and error messages for operators

### Integration Success Criteria

- [ ] **Koji-Boxed Compatibility**: Works with koji-boxed hub and services
- [ ] **Multi-Tag Support**: Handles multiple build tags simultaneously
- [ ] **Multi-Arch Support**: Handles multiple architectures (x86_64, aarch64, etc.)
- [ ] **Hub Compatibility**: Hub cannot distinguish adjutant from mock-based kojid

### Operational Success Criteria

- [ ] **Configuration**: Operators can configure worker via `kojid.conf`
- [ ] **Monitoring**: Key metrics available (task success rate, container overhead, policy cache hits)
- [ ] **Troubleshooting**: Clear error messages and logs for common issues
- [ ] **Documentation**: Complete operator documentation

## Phased Milestones: Breaking Phase 2 into Sub-Phases

### Phase 2.1: Configuration and Policy Foundation (Weeks 1-2)

**Goal**: Enable config parsing and hub policy framework

**Deliverables**:
- Real `kojid.conf` parsing integrated
- `[adjutant]` section support
- PolicyResolver class with hub integration
- Policy caching implementation
- Unit tests for config and policy

**Success Criteria**:
- Worker reads config from `kojid.conf`
- Policy resolver queries hub and caches results
- Fallback to config defaults works

**Dependencies**: None (builds on Phase 1)

### Phase 2.2: Buildroot Implementation + exec() Pattern (Weeks 3-5)

**Goal**: Complete buildroot setup with exec()-based step execution

**Deliverables**:
- **exec() Pattern**: Add `exec()` and `copy_to()` to ContainerManager interface
- **Step-by-step execution**: Replace bash -c with explicit command execution
- **Config file placement**: Copy yum repos, RPM macros directly to /etc
- Dependency resolution via koji API
- Repository configuration inside containers
- Buildroot initialization with explicit steps
- Integration with BuildArchAdapter
- Tests with real packages (simple and complex)

**Success Criteria**:
- exec() and copy_to() methods implemented and tested
- Config files placed in standard locations (/etc/yum.repos.d/, /etc/rpm/)
- Packages with dependencies build successfully
- Buildroot setup matches mock capabilities
- Integration tests pass with real SRPMs
- Better debugging via explicit step execution

**Dependencies**: Phase 2.1 (needs config for repo URLs)

**Key Enhancement**: exec() pattern enables:
- Cleaner config file management (no heredocs)
- Better error attribution (know which step failed)
- Interactive debugging (exec into running container)
- Incremental progress tracking

### Phase 2.3: Monitoring and Performance (Weeks 6-7)

**Goal**: Add operational monitoring and validate performance

**Deliverables**:
- **Status HTTP Server**: Minimal REST API for worker status
- **Container Registry**: Track active containers and task state
- **Live Monitoring Endpoints**:
  - `/status` - Worker health and capacity
  - `/containers` - Active containers list
  - `/tasks/<id>` - Task details and progress
  - `/tasks/<id>/logs` - Live log streaming
- **Optional Dashboard**: Simple HTML page with auto-refresh
- Benchmark suite (container vs mock)
- Performance analysis and optimization
- Documentation of performance characteristics
- Performance regression tests

**Success Criteria**:
- Status server accessible via HTTP (localhost:8080)
- All active containers visible via API
- Live task status updates available
- Container overhead < 20% (simple), < 30% (complex)
- No performance regressions
- Benchmark results documented

**Dependencies**: Phase 2.2 (needs complete buildroot for accurate benchmarks)

**Key Enhancement**: Monitoring enables:
- Real-time visibility into worker state
- Easy debugging (see what containers are running)
- Progress tracking (know which step a task is on)
- Operational dashboards (integrate with monitoring systems)

### Phase 2.4: Testing and Production Readiness (Weeks 8-9)

**Goal**: Comprehensive testing, documentation, and production validation

**Deliverables**:
- Test coverage at 80%+
- Failure mode tests
- Integration tests with koji-boxed
- Operator documentation
- Troubleshooting guide
- Monitoring integration guide
- Production deployment checklist

**Success Criteria**:
- All test categories complete
- Documentation complete
- Monitoring validated
- Ready for production deployment
- Integration with koji-boxed verified

**Dependencies**: Phase 2.1-2.3 (all features implemented)

## Dependencies and Prerequisites

### External Dependencies

- **Koji Library**: `koji.read_config_files()` for config parsing
- **Koji Hub API**: Policy query endpoints, buildroot API, repo API
- **Podman**: Continued support for podman-py API
- **Koji-Boxed**: Integration testing environment

### Internal Dependencies

- **Phase 1 Completion**: All Phase 1 features must be stable
- **ADR Compliance**: Phase 2 must comply with ADR 0001 and ADR 0002
- **Interface Stability**: Phase 1 interfaces (`ContainerManager`, `ContainerSpec`) must remain stable

### Prerequisites

- Understanding of koji buildroot system
- Access to koji-boxed environment for integration testing
- Representative test packages for benchmarking
- Koji hub with policy API (or mock hub for testing)

## Coordination Plan

### Personality Assignments

- **Strategic Planner**: This roadmap, milestone tracking, risk monitoring
- **Systems Architect**: Hub policy API design, config parsing architecture
- **Implementation Lead**: Code implementation (config, policy, buildroot)
- **Container Engineer**: Buildroot containerization, performance optimization
- **Quality Engineer**: Test strategy, coverage targets, benchmark methodology

### Handoffs

1. **Strategic Planner → Systems Architect**: Policy API design requirements
2. **Systems Architect → Implementation Lead**: Config parsing and policy implementation
3. **Implementation Lead → Container Engineer**: Buildroot containerization
4. **Container Engineer → Quality Engineer**: Performance benchmarks
5. **Quality Engineer → Strategic Planner**: Phase 2 validation

### Communication

- Weekly milestone reviews
- Risk assessment updates
- Test coverage reports
- Performance benchmark results

## Conclusion

Phase 2 transforms koji-adjutant from a functional prototype into a production-ready build worker. By implementing hub policy integration, real configuration management, complete buildroot setup, and performance validation, Phase 2 addresses all critical gaps for production deployment.

The phased milestone approach breaks Phase 2 into manageable sub-phases, each building on the previous. Success criteria are clear and measurable, ensuring we know when Phase 2 is complete.

**Phase 2: READY TO BEGIN** 🚀

---

*Next Steps*:
1. Systems Architect designs hub policy API
2. Implementation Lead implements config parsing
3. Container Engineer designs buildroot containerization
4. Quality Engineer establishes benchmark methodology
