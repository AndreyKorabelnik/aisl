# Test status — code-analyzer-core 0.44.13

## Automated
- targeted System Description / typed evidence / navigation / profile tests: **20 passed**
- `compileall`: **OK**

## Real AT900 client-profile acceptance
- `system-description-evidence/v1`: **completed**
- expected compact artifacts: **7/7**
- inbound scenarios: **59**
- scenarios with observed storage: **33**
- scenarios with observed outbound HTTP: **2**
- scenarios with bounded observed call chain: **39**
- composition status `observed_source_call_chain`: **33**
- representative REST/Kafka scenarios reach concrete service/DAO/outbound operations.

## Known limits
- intentionally conservative: ambiguous implementation sets are not traversed;
- not every inbound scenario is expected to have a proven downstream boundary;
- no runtime-dispatch/business-process inference.
