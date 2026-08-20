# Change Report — Preflight Selective Execution Block F

Date: 2026-08-16  
Status: **VALIDATION-ONLY / COMPLETE**

## Runtime change

None.

Block F does not change Core, Runner, KLC, Prepared Runtime, Knowledge API, KCP, or any other runtime package. All nine package trees are byte-identical to the released Block E canonical.

## Added release evidence

- four-case real baseline-vs-selective acceptance;
- eight captured knowledge execution plans (baseline + selective for four repositories);
- package byte-identity proof against Block E;
- Block F acceptance, test status, and handover documentation.

## Validation cases

1. Java/config gateway: no analyzer omitted when all current predicates are applicable.
2. Scala/SQL/YAML datamart: Java-only interaction analysis omitted.
3. SQL/JSON/YAML insurance repository: Java-only interaction analysis omitted.
4. Java/XML UCP data model: structured JSON/YAML shape analysis omitted.

No predicate was widened to improve skip counts. No repository-specific exception was introduced.

## Versions

Unchanged from Block E:

- evidence-common `0.23.2`
- code-analyzer-core `0.44.23a7`
- static-analysis-runner `0.10.27`
- prepared-knowledge-runtime `0.1.0.post10`
- knowledge-layer-core `0.61.0a35`
- knowledge-integration `0.1.15`
- knowledge-api `0.35.0`
- knowledge-reporting `0.18.1`
- knowledge-control-plane `1.2.0a27`
- aisl-contract `0.3.0b8`

## Architectural conclusion

Selective execution remains a mechanical consumer of Core-owned applicability; no second planner, concept-based hard-skip path, analyzer inspection, or silent fallback was added.
