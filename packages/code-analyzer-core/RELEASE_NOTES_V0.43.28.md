# code-analyzer-core 0.43.28 — Java persistence mapping evidence

Core now publishes a second independent evidence family through the generic evidence runtime:

`java-persistence-mapping-evidence/v1`

## Architecture

- Added `java-persistence-mapping-analyzer` to the Core-owned analyzer registry.
- Added explicit entity/table, field/column, key, relationship and inheritance mapping records.
- The analyzer consumes observed Java declarations and annotation parameters only.
- JPA default table/column naming is not inferred.
- Physical-model matching, naming similarity and observed storage use are forbidden in Core evidence.
- Runner production code is unchanged for this evidence family.
- No legacy stage route, compatibility adapter, fallback or dual-write is provided.

## Supported v1 declarations

- `Entity`, `MappedSuperclass`, `Embeddable`, `Table`;
- `Id`, `EmbeddedId`, `IdClass`, `Column`;
- `OneToOne`, `OneToMany`, `ManyToOne`, `ManyToMany`, `JoinColumn`, `MapsId`;
- `Embedded`, `Transient`, `Version`, `Basic`, `Enumerated`, `Convert`;
- `Inheritance`, `DiscriminatorColumn`, `DiscriminatorValue`.

Composite annotations such as `JoinColumns`, `JoinTable` and `AttributeOverrides` remain raw source evidence and produce explicit diagnostics in v1.
