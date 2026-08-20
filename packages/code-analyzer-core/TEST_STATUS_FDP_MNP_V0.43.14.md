# Test status — FDP MNP inheritance dispatch — code-analyzer-core 0.43.14

## Completed step

Source-proven Java inheritance dispatch is available to the FDP interprocedural index.
The AT900 template-method bridge is now visible:

`KafkaMNPConsumer.updateOperator → AbstractDalResultHandler.handle → doHandleByDal → PhoneOperatorHandler.handleByDal`.

## Tests

- focused inheritance/template-method regression: passed;
- existing custom DAO provenance regression: passed;
- total focused result: `2 passed, 25 deselected`;
- compileall: passed;
- source manifest and ZIP integrity: passed during packaging.

## Known limitation

This step restores method connectivity only. The transformed field provenance through
`Collectors.toMap`, local `Map.get`, DTO setters and collection elements is addressed
in the next iteration.
