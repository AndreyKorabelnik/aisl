# Analysis UI 2.0.0a35

Iteration 111 makes the complete Knowledge Assistant `attribute-addition-plan/v1` profile mandatory for standard prepared-context chat. The UI no longer maintains a shortened copy of attribute-addition rules.

Every successful answer reports the loaded profile ID, version, SHA-256 fingerprint and load status in diagnostics. A missing packaged profile now produces explicit `assistant_profile_unavailable` instead of silently falling back to reduced behavior.
