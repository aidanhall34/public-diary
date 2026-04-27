from collections.abc import Iterator
from pathlib import Path

import pytest
from public_diary_tools.config import (
    DrivePathSelection,
    active_user_member,
    browse_drive_path,
    build_act_vars,
    select_project,
    select_repository,
)


class FakeGoogle:
    def create_project(self, project_id: str, name: str) -> None:
        raise AssertionError((project_id, name))

    def project_number(self, project_id: str) -> str:
        assert project_id == "proj"
        return "123"

    def list_projects(self) -> list[str]:
        return ["proj"]

    def list_shared_drives(self) -> list[tuple[str, str]]:
        return [("drive-id", "Diary")]

    def list_my_drive_top_level_folders(self) -> list[tuple[str, str]]:
        return [("my-folder-id", "My Vault")]

    def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
        assert shared_drive_id == "drive-id"
        return [("folder-id", "Vault")]

    def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]:
        assert shared_drive_id in {"", "drive-id"}
        return {"drive-id": [("folder-id", "Vault")], "folder-id": []}.get(parent_id, [])

    def folder_info(self, folder_id: str) -> tuple[str, str]:
        return {
            "drive-id": ("Diary", ""),
            "folder-id": ("Vault", "drive-id"),
            "my-folder-id": ("My Vault", ""),
        }.get(folder_id, (folder_id, ""))


def test_build_act_vars_derives_dynamic_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    answers: Iterator[str] = iter(["y", "1", "", ".", "1", "1"])

    values = build_act_vars(FakeGoogle(), input_fn=lambda _: next(answers)).as_env()

    provider = "projects/123/locations/global/workloadIdentityPools/github/providers/public-diary"
    assert values == {
        "GCP_WORKLOAD_IDENTITY_PROVIDER": provider,
        "GCP_SERVICE_ACCOUNT": "public-diary-deploy@proj.iam.gserviceaccount.com",
        "GOOGLE_DRIVE_ROOT_FOLDER_ID": "",
        "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id",
        "GOOGLE_WORKSPACE_USER": "",
        "GOOGLE_DRIVE_PATH": "",
    }


def test_build_act_vars_prompts_for_shared_drive_when_none_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class NoDriveGoogle(FakeGoogle):
        def list_shared_drives(self) -> list[tuple[str, str]]:
            return []

        def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
            return []

    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    answers: Iterator[str] = iter(["y", "1", ".", "", "1", "1"])

    values = build_act_vars(NoDriveGoogle(), input_fn=lambda _: next(answers)).as_env()

    assert values["GOOGLE_DRIVE_SHARED_DRIVE_ID"] == ""
    assert values["GOOGLE_DRIVE_ROOT_FOLDER_ID"] == "my-folder-id"


def test_build_act_vars_allows_custom_shared_drive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class NoDriveGoogle(FakeGoogle):
        def list_shared_drives(self) -> list[tuple[str, str]]:
            return []

        def list_my_drive_top_level_folders(self) -> list[tuple[str, str]]:
            return []

        def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
            assert shared_drive_id == "manual-drive"
            return []

        def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]:
            assert parent_id == "manual-drive"
            assert shared_drive_id == "manual-drive"
            return []

    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    monkeypatch.setenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "manual-drive")
    answers: Iterator[str] = iter(["y", "", ".", "1", "1"])

    values = build_act_vars(NoDriveGoogle(), input_fn=lambda _: next(answers)).as_env()

    assert values["GOOGLE_DRIVE_SHARED_DRIVE_ID"] == "manual-drive"
    assert values["GOOGLE_DRIVE_ROOT_FOLDER_ID"] == ""


def test_browse_drive_path_can_select_current_child_and_parent() -> None:
    class FolderGoogle(FakeGoogle):
        def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]:
            assert shared_drive_id == "drive-id"
            return {
                "root": [("dir-id", "dir")],
                "dir-id": [("subdir-id", "subdir")],
                "subdir-id": [],
            }.get(parent_id, [])

    answers: Iterator[str] = iter(["2", "3", "1"])

    selected = browse_drive_path(FolderGoogle(), "drive-id", "root", input_fn=lambda _: next(answers))
    assert selected == DrivePathSelection(root_folder_id="root", path="dir/subdir")

    answers = iter(["2", "3", "2", "1"])

    selected = browse_drive_path(FolderGoogle(), "drive-id", "root", input_fn=lambda _: next(answers))
    assert selected == DrivePathSelection(root_folder_id="root", path="dir")


def test_browse_drive_path_can_move_above_starting_folder() -> None:
    class FolderGoogle(FakeGoogle):
        def folder_info(self, folder_id: str) -> tuple[str, str]:
            return {
                "root": ("root", "parent-id"),
                "parent-id": ("parent", ""),
            }.get(folder_id, (folder_id, ""))

        def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]:
            assert shared_drive_id == ""
            return {"parent-id": [("root", "root")], "root": []}.get(parent_id, [])

    answers: Iterator[str] = iter(["..", "."])

    assert browse_drive_path(FolderGoogle(), "", "root", input_fn=lambda _: next(answers)) == DrivePathSelection(
        root_folder_id="parent-id",
        path="",
    )


def test_browse_drive_path_allows_manual_path_without_root() -> None:
    answers: Iterator[str] = iter(["3", "dir/subdir"])

    assert browse_drive_path(FakeGoogle(), "", "", input_fn=lambda _: next(answers)) == DrivePathSelection(
        root_folder_id="",
        path="dir/subdir",
    )


def test_select_project_uses_configured_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr("public_diary_tools.config.configured_gcloud_project", lambda: "configured")
    assert select_project(FakeGoogle()) == "configured"


def test_select_project_prompts_when_no_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class NoProjectsGoogle(FakeGoogle):
        def list_projects(self) -> list[str]:
            return []

        def create_project(self, project_id: str, name: str) -> None:
            calls.append((project_id, name))

    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr("public_diary_tools.config.configured_gcloud_project", lambda: "")
    projects: list[str] = []
    monkeypatch.setattr("public_diary_tools.config.set_gcloud_project", projects.append)

    assert select_project(NoProjectsGoogle(), input_fn=lambda _: "manual") == "manual"
    assert calls == [("manual", "Obsidian publishing")]
    assert projects == ["manual"]


def test_select_project_retries_blank_custom_project(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class NoProjectsGoogle(FakeGoogle):
        def list_projects(self) -> list[str]:
            return []

        def create_project(self, project_id: str, name: str) -> None:
            calls.append((project_id, name))

    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr("public_diary_tools.config.configured_gcloud_project", lambda: "")
    projects: list[str] = []
    monkeypatch.setattr("public_diary_tools.config.set_gcloud_project", projects.append)
    answers: Iterator[str] = iter(["", "manual"])

    assert select_project(NoProjectsGoogle(), input_fn=lambda _: next(answers)) == "manual"
    assert calls == [("manual", "Obsidian publishing")]
    assert projects == ["manual"]


def test_select_repository_uses_current_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr("public_diary_tools.config.repository_from_gh", lambda: "owner/repo")

    assert select_repository(input_fn=lambda _: "1") == "owner/repo"


def test_select_repository_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")

    assert select_repository(input_fn=lambda _: "ignored") == "env/repo"


def test_select_repository_retries_empty_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    def fail_repo() -> str:
        raise RuntimeError("outside repo")

    monkeypatch.setattr("public_diary_tools.config.repository_from_gh", fail_repo)
    answers: Iterator[str] = iter(["", "owner/repo"])

    assert select_repository(input_fn=lambda _: next(answers)) == "owner/repo"


def test_prompt_wif_defaults_allows_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    answers: Iterator[str] = iter(
        ["n", "2", "deploy", "2", "pool", "2", "provider", "1", "", ".", "1", "1"],
    )

    values = build_act_vars(FakeGoogle(), input_fn=lambda _: next(answers)).as_env()

    assert values["GCP_SERVICE_ACCOUNT"] == "deploy@proj.iam.gserviceaccount.com"
    assert values["GCP_WORKLOAD_IDENTITY_PROVIDER"] == (
        "projects/123/locations/global/workloadIdentityPools/pool/providers/provider"
    )


def test_build_act_vars_ignores_workspace_user_for_shared_drive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    monkeypatch.setenv("GOOGLE_WORKSPACE_USER", "user@example.com")
    answers: Iterator[str] = iter(["y", "1", "", ".", "1", "1"])

    values = build_act_vars(FakeGoogle(), input_fn=lambda _: next(answers)).as_env()

    assert values["GOOGLE_DRIVE_SHARED_DRIVE_ID"] == "drive-id"
    assert values["GOOGLE_WORKSPACE_USER"] == ""


def test_active_user_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("public_diary_tools.config.active_gcloud_account", lambda: "user@example.com")
    assert active_user_member() == "user:user@example.com"
