# knowledge-api 0.10.0

The SQL relation endpoint now defaults to a business-source view. Technical intermediates and local output targets remain queryable through `view=technical` and `view=all`.

Each relation exposes:

- semantic role;
- classification status;
- classification reasons;
- default visibility;
- local write and downstream target counts;
- repository-owned namespace and technical-name signals.

The API requires `knowledge-layer-core>=0.51.0,<1.0.0`.
