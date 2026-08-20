# Knowledge Layer Core 0.61.0a27

Clarifies materialization output semantics: `outputs.capabilities` are guaranteed outputs, while `outputs.conditional_capabilities` may be published only when the corresponding optional evidence was actually evaluated. Repository Inventory therefore no longer promises `common.repository-structural-members` when structured-member evidence is absent; it still publishes that capability when the evidence is present and evaluated.
