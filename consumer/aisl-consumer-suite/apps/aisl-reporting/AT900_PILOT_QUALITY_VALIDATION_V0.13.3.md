# AT900 pilot-quality validation — aisl-reporting 0.13.3

## Scope

This iteration evaluates one real system, AT900 `client-profile`, for the currently applicable pilot profiles:

1. System description.
2. Data model.
3. Foreign data persistence (existing confirmed/partial evidence reused as a regression baseline).

Intersystem-dependency quality and SQL-mart-change quality are not forced onto AT900; they require suitable multi-system and SQL-datamart fixtures.

## Fresh deterministic baseline

The suite `default-system-analysis` completed on 1,038 files and published a Knowledge Layer with `suite.system-description`, `suite.data-model`, `common.data-model`, and `common.physical-model`.

Observed counts:

- project modules: 4;
- inbound REST operations: 35;
- inbound Kafka consumers: 24;
- outbound HTTP integrations: 6;
- outbound Kafka publications: 7;
- physical tables: 80;
- columns: 639;
- keys: 55;
- declared database relationships: 13;
- physical relationship observations: 192;
- diagnostic gap occurrences: 7,462.

## Defects found and corrected

### 1. System-description dataset exceeded its own intent

Before 0.13.3, the pretty dataset was approximately 778 KB and duplicated interfaces, integrations, relationships and evidence payloads. The `standard` detail limit did not constrain the selected relationships.

After 0.13.3:

- canonical validation size: 218,518 bytes;
- complete boundary counts remain available;
- the full boundary catalog is compact;
- exact provenance remains in 14 selected interface-map entries and representative journeys;
- 20 relationships, 25 representative objects, 16 dependencies and 20 technical references are selected for the standard report.

### 2. Technical vocabulary was presented as business capability candidates

Before 0.13.3, top labels included `topic`, `receive`, `name`, `message`, `mbk`, and `cache`.

After 0.13.3, interface-backed source-diverse labels are:

- `card`;
- `phone`;
- `profile`;
- `push`;
- `device`;
- `history`;
- `block`;
- `migrate`.

Transport/configuration tokens and identifier-like acronyms do not create capabilities by themselves.

### 3. Data groups were dominated by the schema prefix

Before 0.13.3, 73 tables were grouped under `mbk` and `cache`.

After 0.13.3, groups are derived from simple table names and may overlap. Leading groups include `history`, `card`, `link`, `phone`, `block`, `device`, `notification`, and `push`.

### 4. Physical-only data model was described as a fallback

AT900 exposes a rich physical model but no logical object inventory in the selected suite. This is now explicit:

- `report_mode=physical_only`;
- `focus_status=not_applicable_no_logical_objects`;
- logical model status: `not_observed`;
- physical model status: `observed`;
- physical object count: 80;
- physical relationship count: 192.

The report contract treats the physical model as the primary observed model and prohibits invented logical entities.

## FDP regression baseline

The previously validated exact FDP catalog remains the baseline:

- 945 exact source-field-access cases;
- 11 confirmed same-data cases retained in the report;
- confirmed `PHONE.OPERATORID` path to `/mbClientProfileExtended`;
- separate confirmed `DEVICE_LINK.CLIENT_ID`, `DEVICE_LINK.DEVICE_ID`, and `DEVICE_LINK.UCP_ID` cases;
- the card-migration path remains partial and must be shown as unresolved rather than completed by approximation.

No Core or KLC change was required by the AT900 reporting-quality findings.

## Quality matrix

| Area | Expected | Actual after 0.13.3 | Status |
|---|---|---|---|
| Module structure | Four project modules visible | Four modules observed | confirmed |
| Interface inventory | REST/Kafka inbound and HTTP/Kafka outbound preserved | 35/24/6/7 | confirmed |
| Report budget | Standard dataset bounded | 218,518 canonical bytes | confirmed |
| Capability labels | Business-oriented candidates, no transport/config labels | card/phone/profile/push/device/... | confirmed |
| Physical data model | Tables, keys and observed relationships remain usable | 80 tables, 55 keys, 192 observations | confirmed |
| Logical data model | Absence stated explicitly | `not_observed` | confirmed absence |
| Data-model mode | No hidden substitution | `physical_only` | confirmed |
| FDP DEVICE_LINK | Exact field/path cases remain separate | CLIENT_ID/DEVICE_ID/UCP_ID confirmed | confirmed |
| FDP MNP | OPERATORID path remains isolated | confirmed | confirmed |
| FDP card migration | Partial chain not promoted | unresolved/partial | expected partial |
| Live LLM prose/chat | Requires configured model endpoint | not executed in this iteration | not validated |

## Decision

AT900 is completed for deterministic pilot evidence and reporting contracts for system description, physical data model, and existing FDP cases. The remaining AT900 activity is user acceptance of live generated prose/chat when a model endpoint is available; no additional generic analysis algorithm is justified by the current findings.
