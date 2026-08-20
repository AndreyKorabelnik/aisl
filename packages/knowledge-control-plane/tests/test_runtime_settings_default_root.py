from knowledge_control_plane.runtime.settings import RuntimeSettings


def test_default_runtime_root_is_runtime_control_plane(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_CONTROL_PLANE_RUNTIME_ROOT", raising=False)
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    assert settings.runtime_root == (tmp_path / "runtime" / "control-plane").resolve()


def test_runtime_root_env_override_remains_authoritative(tmp_path, monkeypatch):
    override = tmp_path / "custom-runtime"
    monkeypatch.setenv("KNOWLEDGE_CONTROL_PLANE_RUNTIME_ROOT", str(override))
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    assert settings.runtime_root == override.resolve()
