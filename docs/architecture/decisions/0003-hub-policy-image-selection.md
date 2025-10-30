---
title: "ADR 0003: Hub Policy-Driven Container Image Selection"
status: Accepted
date: 2025-01-27
deciders: Systems Architect, Implementation Lead
---

## Context

Phase 1 established a single default container image (`adjutant_task_image_default`) for all tasks, which suffices for proof-of-concept but is insufficient for production deployments. Production koji systems require different container images per build tag (e.g., `f39-build` vs `el10-build`), architecture (x86_64 vs aarch64), and potentially task type (buildArch vs createrepo vs imageBuild).

**Problem Statement**: Phase 1's hardcoded single-image approach cannot support:
- Multi-tag deployments (different distros per tag)
- Multi-arch deployments (architecture-specific images)
- Task-type-specific images (specialized images for different task types)
- Hub-controlled policy updates without worker config changes

**Requirements from Phase 2 Roadmap**:
- Dynamic image selection per build tag / task type / architecture
- Hub provides policy via API (hub is source of truth)
- Policy format: JSON-based with fallback strategy
- Caching for performance (reduce hub query overhead)
- Backward compatibility with Phase 1 default
- No breaking changes to Phase 1 `ContainerManager` interface

## Decision

We implement a hub-driven policy system where:
1. **Hub stores image selection policies** in tag extra data or global configuration
2. **Worker queries hub** for policy applicable to current task via XMLRPC API
3. **Policy evaluation engine** matches rules by precedence: tag+arch → tag → task_type → default
4. **Caching layer** reduces hub query overhead (TTL-based cache per tag/arch combination)
5. **Graceful fallback** to config default when hub unavailable or policy missing
6. **No interface changes** to `ContainerManager`; policy resolution happens before `ContainerSpec` construction

### Architecture Overview

```
┌─────────────────┐
│   Koji Hub      │
│                 │
│  Tag Extra Data │──┐
│  or Config      │  │
│  (JSON Policy)  │  │
└─────────────────┘  │
                     │ XMLRPC Query
                     │ (getTagExtra, getBuildConfig)
┌─────────────────┐  │
│   Worker        │  │
│                 │  │
│  PolicyResolver │◄─┘
│     ↓           │
│  Cache (TTL)    │
│     ↓           │
│  Image Selected │──► ContainerSpec.image
└─────────────────┘
```

## Design Details

### Policy Format

Policy is stored as JSON in hub tag extra data (preferred) or build config extra data (fallback). The JSON structure supports multiple rule types with explicit precedence.

**Policy JSON Schema**:
```json
{
  "adjutant_image_policy": {
    "version": "1.0",
    "rules": [
      {
        "type": "tag_arch",
        "tag": "f39-build",
        "arch": "x86_64",
        "image": "registry/koji-adjutant-task:f39-x86_64"
      },
      {
        "type": "tag_arch",
        "tag": "f39-build",
        "arch": "aarch64",
        "image": "registry/koji-adjutant-task:f39-aarch64"
      },
      {
        "type": "tag",
        "tag": "el10-build",
        "image": "registry/koji-adjutant-task:el10"
      },
      {
        "type": "task_type",
        "task_type": "buildArch",
        "image": "registry/koji-adjutant-task:build"
      },
      {
        "type": "task_type",
        "task_type": "createrepo",
        "image": "registry/koji-adjutant-task:repo"
      },
      {
        "type": "default",
        "image": "registry/koji-adjutant-task:default"
      }
    ]
  }
}
```

**Rule Types and Precedence** (evaluated in order):
1. `tag_arch`: Match specific tag + architecture combination (highest priority)
2. `tag`: Match tag regardless of architecture
3. `task_type`: Match task type (e.g., `buildArch`, `createrepo`, `imageBuild`)
4. `default`: Fallback when no other rule matches (lowest priority)

**Policy Location**:
- **Primary**: Tag extra data key `adjutant_image_policy` on build tag
- **Fallback**: Build config extra data `adjutant_image_policy` (if tag extra unavailable)
- **Worker override**: Config default `adjutant_task_image_default` (if hub unavailable)

### Hub API Contract

**Method 1: Query Tag Extra Data** (Primary)
```python
# Via koji session
tag_info = session.getTag(tag_name, event=event_id)
extra_data = tag_info.get('extra', {})
policy_json = extra_data.get('adjutant_image_policy')
```

**Method 2: Query Build Config** (Fallback if tag extra unavailable)
```python
# Via koji session
build_config = session.getBuildConfig(tag_name, event=event_id)
extra_data = build_config.get('extra', {})
policy_json = extra_data.get('adjutant_image_policy')
```

**API Requirements**:
- Worker must have authenticated session to hub (existing kojid authentication)
- Worker must handle missing extra data gracefully (return None, fallback to config)
- Worker must handle JSON parse errors gracefully (log error, fallback to config)
- Worker must handle hub unavailability gracefully (fallback to config, log warning)

**Task Context Available for Policy Resolution**:
- `tag_name` (build tag, e.g., `f39-build`) - from task params `root` field
- `arch` (architecture, e.g., `x86_64`) - from task params `arch` field
- `task_type` (e.g., `buildArch`, `createrepo`) - from task handler type
- `event_id` (optional) - from task context if available

### Policy Evaluation Engine

**Implementation**: `PolicyResolver` class in `koji_adjutant/policy.py`

**Core Method**:
```python
def resolve_image(
    self,
    tag_name: str,
    arch: str,
    task_type: str,
    event_id: Optional[int] = None,
) -> str:
    """Resolve container image from hub policy or config fallback.
    
    Evaluation order:
    1. Check cache (by tag+arch key)
    2. Query hub for policy (tag extra → build config extra)
    3. Evaluate rules in precedence order
    4. Cache result (if from hub)
    5. Fallback to config default if no match
    
    Returns:
        Container image reference (e.g., "registry/image:tag")
    """
```

**Evaluation Algorithm**:
```python
# Pseudocode
policy = self._get_policy_from_hub(tag_name, event_id) or self._get_cached_policy(tag_name)

if policy:
    for rule in policy['rules']:
        if rule['type'] == 'tag_arch' and rule['tag'] == tag_name and rule['arch'] == arch:
            return rule['image']
        if rule['type'] == 'tag' and rule['tag'] == tag_name:
            return rule['image']
        if rule['type'] == 'task_type' and rule['task_type'] == task_type:
            return rule['image']
        if rule['type'] == 'default':
            return rule['image']  # Store as fallback, continue to check other rules
    
    # If policy exists but no rule matched, use default from policy
    return policy_default_image or self._config_default()
else:
    # No policy available, use config default
    return self._config_default()
```

**Error Handling**:
- Hub query failure: Log warning, return config default, don't cache failure
- JSON parse error: Log error, return config default, don't cache failure
- Policy version mismatch: Log warning, attempt to parse (forward compatibility), fallback if incompatible
- Image validation: Worker doesn't validate image exists; `ContainerManager.ensure_image_available()` handles pull failures

### Caching Strategy

**Cache Key**: `(tag_name, arch)` tuple (covers most specific matching)
- Single cache entry per tag+arch combination
- Prevents redundant hub queries for same tag/arch tasks

**Cache TTL**: Configurable via `adjutant_policy_cache_ttl` (default: 300 seconds / 5 minutes)
- Short enough to pick up policy changes quickly
- Long enough to reduce hub query overhead significantly

**Cache Implementation**:
```python
@dataclass
class CachedPolicy:
    policy: dict
    cached_at: datetime
    ttl_seconds: int
    
    def is_valid(self) -> bool:
        age = (datetime.now() - self.cached_at).total_seconds()
        return age < self.ttl_seconds
```

**Cache Invalidation**:
- TTL expiration (automatic)
- Manual invalidation via `PolicyResolver.invalidate_cache(tag_name, arch)`
- Worker restart (cache cleared)

**Cache Storage**: In-memory dict (Phase 2)
- Future enhancement: Persistent cache (file-based or Redis) for multi-worker coordination

**Performance Considerations**:
- Cache hit: ~0ms (in-memory lookup)
- Cache miss + hub query: ~50-200ms (depends on hub latency)
- Expected cache hit rate: >90% for typical workloads (same tag/arch tasks clustered)

### Fallback Behavior

**Fallback Chain** (in order):
1. **Hub policy match** (tag_arch → tag → task_type → default rule)
2. **Policy default rule** (if policy exists but no specific match)
3. **Config default** (`adjutant_task_image_default` from `kojid.conf`)
4. **Hardcoded Phase 1 default** (`registry/almalinux:10` - final fallback)

**Graceful Degradation**:
- Hub unavailable: Use config default, log warning, continue operation
- Policy parse error: Use config default, log error, continue operation
- No matching rule: Use policy default rule or config default
- Config missing: Use hardcoded Phase 1 default (backward compatibility)

**Operator Control**:
- `adjutant_policy_enabled = true/false` (default: `true`)
  - `false`: Skip hub queries entirely, use config default
  - Useful for testing, air-gapped deployments, or hub downtime scenarios

### Integration Points

**Task Adapter Integration**:
```python
# In BuildArchAdapter.build_spec()
from ..policy import PolicyResolver

# Resolve image from policy
resolver = PolicyResolver(session, config)
image = resolver.resolve_image(
    tag_name=task_params['root'],  # Build tag
    arch=task_params['arch'],
    task_type='buildArch',
    event_id=ctx.event_id,
)

# Use resolved image in ContainerSpec
spec = ContainerSpec(image=image, ...)
```

**Koji Session Dependency**:
- `PolicyResolver` requires authenticated `koji.ClientSession` instance
- Session passed from task handler (already available in kojid task context)
- Session handles authentication (Kerberos/GSSAPI via existing kojid mechanisms)

**Config Integration**:
- `PolicyResolver` reads from `koji_adjutant.config` module (parsed `kojid.conf`)
- Config keys:
  - `adjutant_policy_enabled` (bool, default: `true`)
  - `adjutant_policy_cache_ttl` (int, default: `300`)
  - `adjutant_task_image_default` (string, fallback image)

### Configuration Schema

**`[adjutant]` Section in `kojid.conf`**:
```ini
[adjutant]
# Policy configuration
policy_enabled = true
policy_cache_ttl = 300

# Fallback image (used when policy unavailable or no match)
task_image_default = registry/koji-adjutant-task:almalinux10

# Existing Phase 1 config keys (unchanged)
image_pull_policy = if-not-present
container_mounts = /mnt/koji:/mnt/koji:rw:Z
network_enabled = true
container_timeouts = pull=300,start=60,stop_grace=20
```

**Environment Variable Overrides** (for containerized deployments):
- `KOJI_ADJUTANT_POLICY_ENABLED` (overrides `policy_enabled`)
- `KOJI_ADJUTANT_POLICY_CACHE_TTL` (overrides `policy_cache_ttl`)
- `KOJI_ADJUTANT_TASK_IMAGE_DEFAULT` (overrides `task_image_default`)

### Migration Path from Phase 1

**Phase 1 → Phase 2 Upgrade**:
1. **No config changes required**: Phase 1 config continues to work
   - `adjutant_task_image_default` becomes fallback image
   - Policy system enabled by default (`policy_enabled = true`)

2. **Hub policy setup** (operator action):
   - Operator adds `adjutant_image_policy` JSON to tag extra data for build tags
   - Worker automatically picks up policy on next task (after cache TTL)

3. **Gradual migration**:
   - Tags without policy: Worker uses config default (Phase 1 behavior)
   - Tags with policy: Worker uses hub policy (Phase 2 behavior)
   - No downtime required

4. **Rollback**: Set `policy_enabled = false` to disable policy system, revert to Phase 1 behavior

**Backward Compatibility Guarantees**:
- Phase 1 code paths remain functional (config default always available)
- `ContainerManager` interface unchanged (policy resolution is transparent)
- Task adapters continue to work (policy resolution is additive)

## Consequences

### Positive Consequences

1. **Production Readiness**: Enables multi-tag, multi-arch deployments without code changes
2. **Hub Authority**: Hub controls image selection, enabling centralized policy management
3. **Performance**: Caching reduces hub query overhead (expected >90% cache hit rate)
4. **Flexibility**: Supports complex policy rules (tag+arch, task-type-specific images)
5. **Graceful Degradation**: Fallback chain ensures operation even when hub unavailable
6. **No Breaking Changes**: Phase 1 compatibility maintained

### Negative Consequences

1. **Complexity**: Adds policy evaluation engine, caching layer, and hub integration
2. **Hub Dependency**: Worker depends on hub availability for policy (mitigated by fallback)
3. **Cache Consistency**: Cache TTL means policy changes may take up to TTL seconds to propagate
4. **Testing Overhead**: Requires mock hub for unit tests, real hub for integration tests
5. **Operator Burden**: Operators must understand policy JSON format and tag extra data management

### Performance Impact

**Expected Overhead**:
- Cache hit: ~0ms (negligible)
- Cache miss: +50-200ms per task (hub query latency)
- **Mitigation**: Cache TTL reduces hub queries; typical workloads see <10% cache miss rate

**Optimization Opportunities**:
- Batch policy queries for multiple tags (future enhancement)
- Prefetch policies on worker startup for common tags (future enhancement)
- Persistent cache shared across worker restarts (future enhancement)

### Security Considerations

1. **Hub Authentication**: Policy queries use existing kojid authentication (Kerberos/GSSAPI)
2. **Policy Validation**: Worker validates JSON structure but doesn't validate image references (pull failures handled by ContainerManager)
3. **Cache Poisoning**: In-memory cache is local to worker process (not a security concern)
4. **Hub Trust**: Worker trusts hub-provided policy; hub compromise could affect image selection (mitigated by image pull validation)

## Alternatives Considered

### Alternative 1: Config-Only Image Selection
**Approach**: Expand `kojid.conf` with tag-specific image mappings
**Rejected Because**:
- Requires worker config changes for each new tag (operational burden)
- Hub cannot control policy without worker redeployment
- Doesn't support dynamic policy updates

### Alternative 2: Task Options-Based Image Selection
**Approach**: Hub passes image in task options/parameters
**Rejected Because**:
- Requires hub changes (beyond Phase 2 scope)
- Doesn't support caching (every task includes image)
- Less flexible than policy rules (no fallback chain)

### Alternative 3: Worker-Managed Policy File
**Approach**: Worker reads policy from local file (YAML/JSON), periodically refreshed
**Rejected Because**:
- Hub doesn't control policy (violates "hub is source of truth" principle)
- Requires file distribution mechanism (operational complexity)
- Less flexible than hub API queries

### Alternative 4: Tag-Based Image Naming Convention
**Approach**: Infer image from tag name (e.g., `f39-build` → `image:f39-build`)
**Rejected Because**:
- Too rigid (doesn't support custom mappings)
- Doesn't support architecture-specific images cleanly
- Doesn't support task-type-specific images

### Alternative 5: Separate Policy Service
**Approach**: Dedicated microservice for policy resolution (external to hub)
**Rejected Because**:
- Overkill for Phase 2 scope
- Adds operational complexity (another service to manage)
- Hub already has tag/config infrastructure we can leverage

## Work Items for Implementation Lead

### Phase 2.1: Policy Foundation

1. **Create `koji_adjutant/policy.py`**:
   - Implement `PolicyResolver` class
   - Hub query methods (`_get_policy_from_hub()`)
   - Policy evaluation engine (`resolve_image()`)
   - Cache implementation (`CachedPolicy`, TTL management)

2. **Update `koji_adjutant/config.py`**:
   - Add `adjutant_policy_enabled` config key (default: `true`)
   - Add `adjutant_policy_cache_ttl` config key (default: `300`)
   - Integrate with real `kojid.conf` parsing (Phase 2.1 requirement)

3. **Update Task Adapters**:
   - `BuildArchAdapter.build_spec()`: Use `PolicyResolver.resolve_image()`
   - `CreaterepoAdapter.build_spec()`: Use `PolicyResolver.resolve_image()`
   - Pass koji session from task context to `PolicyResolver`

4. **Unit Tests**:
   - Test policy evaluation (all rule types, precedence)
   - Test caching (TTL expiration, invalidation)
   - Test fallback chain (hub unavailable, parse errors, no match)
   - Test with mock hub session

5. **Integration Tests**:
   - Test with real hub (tag extra data query)
   - Test cache behavior (multiple tasks, same tag/arch)
   - Test fallback scenarios (hub down, missing policy)

### Testing Requirements

**Unit Test Coverage Target**: 85%+ for `policy.py`

**Test Scenarios**:
- Policy evaluation: tag_arch match, tag match, task_type match, default fallback
- Cache: hit, miss, TTL expiration, manual invalidation
- Fallback: hub unavailable, JSON parse error, missing policy, no matching rule
- Edge cases: empty policy, invalid rule types, malformed JSON

**Integration Test Scenarios**:
- Real hub query (tag extra data)
- Cache across multiple tasks
- Config override (`policy_enabled = false`)
- Migration from Phase 1 (no policy → with policy)

### Documentation Requirements

1. **Operator Guide**: How to configure hub policy (tag extra data format, examples)
2. **Config Reference**: Document `adjutant_policy_*` config keys
3. **Troubleshooting**: Common issues (policy not found, cache issues, fallback behavior)
4. **Migration Guide**: Phase 1 → Phase 2 upgrade steps

## References

- Phase 2 Roadmap: `docs/planning/phase2-roadmap.md`
- ADR 0001: Container Lifecycle and Interface Boundaries
- ADR 0002: Container Image Bootstrap and Security
- Koji Tag Extra Data: Hub stores arbitrary JSON in tag `extra` field
- Koji Build Config: `session.getBuildConfig()` returns config with `extra` field

---

**Decision Status**: Accepted for Phase 2.1 implementation.
