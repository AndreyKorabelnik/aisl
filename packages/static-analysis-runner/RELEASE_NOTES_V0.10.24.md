# Static Analysis Runner 0.10.24

Adds generic bulk repository processing without introducing a multi-repository Core/Runner analysis scope.

A Bitbucket project or an existing repository-source manifest is resolved to an operational repository list. Runner then clones one repository into a temporary checkout, executes the normal repository-scoped Knowledge production pipeline, persists only the result/contracts/logs, removes the checkout in `finally`, and proceeds to the next repository. Failure of one repository is explicit in the batch report and does not block later repositories.

The release also distinguishes guaranteed KLC output capabilities from evidence-dependent conditional capabilities so an absent optional enrichment cannot incorrectly fail an otherwise successful single-repository execution.
