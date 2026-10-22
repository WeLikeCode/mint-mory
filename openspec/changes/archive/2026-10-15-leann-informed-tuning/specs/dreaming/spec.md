# Capability: dreaming (delta)

## ADDED Requirements

### Requirement: Hub-aware concept-graph pruning
The dreaming concept-linking step SHALL support giving high-degree "hub" concepts
a larger per-node link budget, so a uniform degree cap cannot sever the links that
keep a memory cluster connected. The behaviour SHALL be opt-in and default to the
existing uniform cap.

#### Scenario: Default reproduces the uniform cap
- **WHEN** `hub_cap_multiplier` is 1.0 (default)
- **THEN** the kept link set is identical to the prior uniform per-node cap.

#### Scenario: Hubs retain more links when enabled
- **WHEN** `hub_cap_multiplier > 1.0` and a concept's candidate-degree is at/above
  the `hub_degree_percentile` threshold
- **THEN** that hub concept may keep up to `int(max_per_node * hub_cap_multiplier)`
  links while non-hub concepts stay capped at `max_per_node`, deterministically.
