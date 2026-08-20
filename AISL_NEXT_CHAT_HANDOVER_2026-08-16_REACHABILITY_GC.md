# AISL Reachability GC — Next Chat Handover

Date: 2026-08-16
Status: **PUBLISHED_PERSISTENCE_LIFECYCLE_COMPLETE**

The persistence initiative now has accepted vertical slices for:

1. observed Core KnowledgeProduct publication;
2. durable AISL Catalog + Artifact Store ownership;
3. producer deletion / consumer autonomy;
4. mixed observed+derived COW and exact dependency integrity;
5. multi-file/sharded observed products;
6. storage-root mobility with identity unchanged;
7. reachability-based GC without refcount dual-write.

Do not automatically add further storage abstractions. Return to product/consumer value unless a concrete operational requirement proves a new persistence gap.

Current GC rule: every retained Catalog revision (active/superseded/inactive) is a reachability root. Retention policy is not implemented by GC. System deletion removes logical reachability; later sweep reclaims bytes not shared by any other retained revision.

Parked scope remains parked.
