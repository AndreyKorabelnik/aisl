# Knowledge Layer Core 0.61.0a23

- Fixes branch correlation when lineage crosses a JOIN into an intermediate table backed by multiple set/UNION branches.
- Uses only observed equality JOIN key + observed inner branch projection state. Branches that explicitly project NULL for the JOIN selector are excluded; ambiguous/unobserved cases are not filtered.
- No Core changes and no source-name hardcoding.
