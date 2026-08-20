# Iteration 24 legacy inventory

| Component | Required by canonical runtime | Decision |
|---|---:|---|
| registry-based system catalog | no | removed |
| `/health` outside canonical prefix | no | removed |
| `/api/v1/**` read routes | no | removed |
| registry/report compatibility models | no | removed |
| KLC typed query adapter | yes | retained and renamed as internal implementation |
| duplicate OpenAPI exporter/schema | no | removed |

The supported runtime is `create_app()` over `/api/knowledge/v1/**` only.
