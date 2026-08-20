# knowledge-control-plane 1.2.0a20

- Breaking extraction of the remaining web frontend into standalone `knowledge-base-generator-ui`.
- Removed Vue/Vite/static-asset ownership and `KNOWLEDGE_CONTROL_PLANE_FRONTEND_DIST`.
- Removed frontend build diagnostic; KCP is now a headless HTTP control-plane service.
- Kept Knowledge API reverse proxy because it remains a generic HTTP service boundary, not a frontend runtime.
- Backend API semantics, Core/Runner/KLC production semantics and Knowledge API publication semantics are unchanged.
