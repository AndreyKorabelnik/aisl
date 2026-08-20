# AT900 FDP card factory validation — 0.43.18

## Observed source code shape

```text
List<MigrateCardRq> requests
→ Collectors.toMap(..., this::createCardUpdate, ...)
→ Map<String, CardUpdate>
```

Inside `createCardUpdate`:

```text
MigrateCard card = req.getData()
cardUpdate.account   = card.financialProductId
cardUpdate.ucpId     = BigInteger(card.epkId), when present
cardUpdate.productId = req.data.productWay4Code, when enabled
```

## Framework result

The factory mapping and stream value projection now preserve:

```text
account   <- data.financialProductId
ucpId     <- data.epkId
productId <- data.productWay4Code
```

`Optional` and conversion wrappers do not erase the explicit getter source.
The result is local/interprocedural propagation evidence only; physical storage
is not claimed by this step.
