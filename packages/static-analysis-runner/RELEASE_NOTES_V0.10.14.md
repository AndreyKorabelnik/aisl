# static-analysis-runner 0.10.14

Legacy Cleanup Block 8 removes the duplicate Runner-owned Core stage taxonomy. The official `core_analysis_catalog/v1` is now the only stage-classification source used or shipped by Runner. Optional Java derived-stage Markdown remains available and is rendered directly from Core-provided contracts. No compatibility taxonomy, dual-read, or Core-source rediscovery fallback is retained.
