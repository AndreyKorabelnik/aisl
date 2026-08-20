# Attribute path resolver v1

`repository_attribute_path/v1` is the only canonical path-composition contract for
attribute lineage.

It traverses only:

- `repository_value_node`;
- `repository_value_flow_edge`.

It does not project paths from generic source observations, does not require execution
contexts and never persists transitive paths.

## Input

- `source`: exact value node ID, occurrence ID, display reference or owner reference;
- `target`: optional exact target reference;
- `selected_repo_ids`: required explicit repository boundary;
- `max_hops`, `max_paths`, `max_branching`;
- optional edge-kind and minimum-confidence filters.

Non-unique source or target references are returned as ambiguity. No candidate is selected
heuristically.

## Output

The resolver returns complete and partial paths. Every step contains the direct edge,
source/target repositories, transformation, naming relation, value preservation,
confidence and provenance.

Partial paths carry explicit gaps such as:

- `no_observed_outgoing_value_flow`;
- `max_hops_reached`;
- `branching_limit_reached`;
- `cycle_prevented`;
- `max_paths_reached`.

Multiple complete paths produce `status=ambiguous`; they are not collapsed.

## Removed legacy

The previous generic `path_queries.py` and source-observation-based `field_flow.py` query
stacks are removed. Their capabilities and evidence commands are not retained as aliases.
