# static-analysis-runner 0.9.56

Removes the duplicate Runner-owned physical-model pipeline and the hidden legacy Knowledge Layer materialization command. Physical models now enter only as explicit `physical-model/v1` typed artifacts and are materialized only through the canonical contract-driven knowledge execution route. No compatibility adapter or fallback is retained.
