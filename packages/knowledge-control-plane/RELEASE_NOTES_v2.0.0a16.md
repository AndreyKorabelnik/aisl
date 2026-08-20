# analysis-ui 2.0.0a16 — source-export discovery and simplified launch UI

## Repository discovery

- Every explicitly selected readable local directory is accepted as source input, even when it has no `.git`, build descriptor, package manifest, conventional extension, or source-layout marker.
- Generic project markers are used only to split a container into independently recognizable direct-child projects; they are not an admission criterion for local code.
- If no child boundary can be proven, the selected directory itself is registered as one repository.
- Maven/Gradle and other exported source trees are still split correctly when their direct children expose project markers.
- Repository metadata records whether discovery came from explicit-directory acceptance or project markers.
- Only missing, unreadable, or uninspectable paths produce warnings.

## Frontend

- Removed the **Шаблон UCP** button, UCP-specific hints/defaults, and its name/package matching heuristic.
- Removed the **Повторно выполнить** and **Принудительно перезапустить** checkboxes from repository and workspace launch forms.
- Browser-created jobs now always use automatic compatible-result reuse. Advanced execution policies remain available through the orchestration API.

## Compatibility

- No public orchestration endpoint was removed.
- Existing persisted repositories and workspaces remain valid.
- Git-backed repositories continue to include revision and branch metadata; exported trees have `revision=null`.
