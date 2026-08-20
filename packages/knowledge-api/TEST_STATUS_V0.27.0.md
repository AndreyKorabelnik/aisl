# knowledge-api 0.27.0 test status

Status: PASS

- Full knowledge-api suite: 72 passed.
- Real clean-Consumer smoke against existing relocated Prepared Knowledge:
  - relation-materializations: HTTP 200;
  - query-context: HTTP 200;
  - data-model/lineage: HTTP 200 (previous contract/schema 500 removed).
- No rematerialization or source analysis was used for the smoke.
- Compileall: PASS.

Security limitation: built-in IAM is outside this proof; industrial external access still requires an authentication/authorization boundary such as API Gateway/service mesh.
