# Test status — aisl-reporting 0.17.3

- Targeted reporting/API/profile validation: 37 passed.
- Real UCP + datamart + PDM + cross-artifact dataset smoke: OK.
- Real dataset size: 441994 bytes (budget 500000).
- Real knowledge supplied to report: 1138 lineage paths, 647 unique logical→physical correspondences, 248 transformations, 10 target data journeys.
- Lineage-aware logical selection includes `Individual`, `Address`, `PhoneNumber`, `DocumentFlag`, `Equivalent` and document/reference types; ambiguous duplicate `Builder` names are not lineage-selected.
- PDM selection begins with the actual `epk_client*`/`epk_lnk_host_id`/`epkid_2_epkid` targets and declared neighbours.
- Representative phone journey includes `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number`.
- `compileall`: OK.
- Source manifest: regenerated and verified.
