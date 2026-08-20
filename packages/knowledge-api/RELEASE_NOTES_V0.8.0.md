# knowledge-api 0.8.0

- Replaced the overloaded relationship object in table details with a compact JOIN contract.
- Preserved source field/cardinality, target identity/aliases, source/target join inputs and confirmation flags.
- Removed logical identity, storage-key evidence, expression trees, parameter bindings and provenance from table-detail relationships.
- Added a relationship-detail endpoint that returns the complete previous technical payload.
- Added focused validation against the saved real UCP `Individual.birthDate` encoded-reference case.
