# Test status — knowledge-layer-core 0.59.18

## Automated
- targeted materialization/reporting/contracts: **16 passed, 1 optional skipped**
- `compileall`: **OK**

## Real AT900 client-profile acceptance
- materialization `system-description`: **completed**
- subject records: **815**
- payload artifacts: **7/7**
- capabilities: system-description/interfaces/scenarios/dependencies
- Reporting dataset with unchanged knowledge-reporting 0.17.3: **built successfully**
- 3 modules, 8 capability clusters, 59 inbound boundaries, 13 outbound integrations, 34 event boundaries, 127 observed storage targets, 8/8 selected representative journeys complete.

## Known limits
- standalone System Description does not invent physical table relationships; relationship section stays empty unless separate data-model knowledge is present.
- module composition is projected from observed Gradle dependency declaration locations; plugin catalog is not materialized by this profile.
