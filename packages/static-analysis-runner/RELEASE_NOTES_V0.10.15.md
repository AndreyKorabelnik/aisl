# static-analysis-runner 0.10.15

Makes completed Prepared Knowledge bundles relocatable across Producer and Consumer environments. `knowledge_execution_result/v1` now records Knowledge Layer `output_path` and `manifest_path` relative to the execution root when the produced artifact is inside that root; artifacts outside the root remain absolute. This uses the existing Knowledge API relative-path resolution contract and does not introduce a new publication/discovery mechanism, compatibility path, or Producer fallback.
