from public_diary_tools.config import active_user_member, build_act_vars, select_project


class FakeGoogle:
    def project_number(self, project_id: str) -> str:
        assert project_id == "proj"
        return "123"

    def list_projects(self) -> list[str]:
        return ["proj"]

    def list_shared_drives(self) -> list[tuple[str, str]]:
        return [("drive-id", "Diary")]

    def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
        assert shared_drive_id == "drive-id"
        return [("folder-id", "Vault")]


def test_build_act_vars_derives_dynamic_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    answers = iter(["", "", "", "", ""])

    values = build_act_vars(FakeGoogle(), input_fn=lambda _: next(answers)).as_env()

    provider = "projects/123/locations/global/workloadIdentityPools/github/providers/public-diary"
    assert values == {
        "GCP_WORKLOAD_IDENTITY_PROVIDER": provider,
        "GCP_SERVICE_ACCOUNT": "public-diary-deploy@proj.iam.gserviceaccount.com",
        "GOOGLE_DRIVE_ROOT_FOLDER_ID": "",
        "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id",
        "GOOGLE_WORKSPACE_USER": "",
        "GOOGLE_DRIVE_PATH": "obs-notes/obs-notes",
    }


def test_build_act_vars_prompts_for_shared_drive_when_none_visible(monkeypatch, tmp_path) -> None:
    class NoDriveGoogle(FakeGoogle):
        def list_shared_drives(self) -> list[tuple[str, str]]:
            return []

        def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
            return []

    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    answers = iter(["manual-drive", "", "", "", ""])

    values = build_act_vars(NoDriveGoogle(), input_fn=lambda _: next(answers)).as_env()

    assert values["GOOGLE_DRIVE_SHARED_DRIVE_ID"] == "manual-drive"
    assert values["GOOGLE_DRIVE_ROOT_FOLDER_ID"] == ""


def test_select_project_uses_configured_project(monkeypatch) -> None:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr("public_diary_tools.config.configured_gcloud_project", lambda: "configured")
    assert select_project(FakeGoogle()) == "configured"


def test_select_project_prompts_when_no_projects(monkeypatch) -> None:
    class NoProjectsGoogle(FakeGoogle):
        def list_projects(self) -> list[str]:
            return []

    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr("public_diary_tools.config.configured_gcloud_project", lambda: "")
    calls = []
    monkeypatch.setattr("public_diary_tools.config.set_gcloud_project", calls.append)

    assert select_project(NoProjectsGoogle(), input_fn=lambda _: "manual") == "manual"
    assert calls == ["manual"]


def test_active_user_member(monkeypatch) -> None:
    monkeypatch.setattr("public_diary_tools.config.active_gcloud_account", lambda: "user@example.com")
    assert active_user_member() == "user:user@example.com"
