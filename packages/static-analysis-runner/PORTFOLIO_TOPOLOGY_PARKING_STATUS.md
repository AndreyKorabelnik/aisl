# Portfolio topology parking status

`portfolio-topology` belongs to the separate Repository Interaction Islands track and is intentionally excluded from the current recovery migration.

Current boundary:
- it is the only remaining entry in the legacy Task registry;
- it is not part of the main knowledge runtime and is not a dependency of SQL, PDM, effective data model, system knowledge, HTTP interactions, value flow, persistence lineage or data-model discovery;
- no Kafka work, Bitbucket streaming changes, island selection changes or topology matching changes are included here;
- no compatibility adapter is introduced between topology and the generic knowledge runtime;
- the current command/task/suite are retained only as a self-contained parked workflow until the Islands track resumes.

Resume the Islands track from its dedicated parking plan, beginning with Kafka evidence inventory. The next recovery step may remove Task/Suite from the main runtime while preserving this parked workflow as a separate boundary.
