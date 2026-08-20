# Analysis UI 2.0.0a69

This release closes the consumer gap found by the final combined-revision E2E.

The standard revision chat still exposes only tools allowed by the capabilities of the pinned
Knowledge API revision. It now also receives the complete canonical
`attribute-addition-plan/v1` interpretation profile. This is required because a combined
UCP + datamart + PDM revision can answer attribute-addition questions without creating a
separate legacy context.

No cross-revision data is inferred, no compatibility adapter is introduced, and the profile
cannot weaken evidence statuses returned by Knowledge API.
