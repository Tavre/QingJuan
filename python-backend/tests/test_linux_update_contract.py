from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LINUX_DEPLOY_DIR = REPOSITORY_ROOT / "deploy" / "linux"


def _read(name: str) -> str:
    return (LINUX_DEPLOY_DIR / name).read_text(encoding="utf-8")


def test_update_uses_fixed_upstream_and_atomic_release_switch() -> None:
    script = _read("update.sh")

    assert 'TRUSTED_UPSTREAM_REF="refs/qingjuan-updater/upstream"' in script
    assert 'fetch --no-tags "$remote_name" "+${merge_ref}:${TRUSTED_UPSTREAM_REF}"' in script
    assert 'expected_revision" != "$fetched_revision' in script
    assert 'git -C "$REPO_DIR" archive --format=tar "$target_revision"' in script
    assert 'switch_current_link "$target_release"' in script
    assert "merge --ff-only" not in script
    assert "pull --ff-only" not in script
    assert script.index('systemctl stop "$SERVICE_NAME"') < script.index(
        'git -C "$REPO_DIR" reset --hard "$target_revision"'
    )


def test_update_keeps_privileged_rollback_outside_service_data() -> None:
    script = _read("update.sh")

    assert 'UPDATER_STATE_DIR="/var/lib/qingjuan-updater"' in script
    assert 'mktemp -d "$UPDATER_STATE_DIR/rollback.' in script
    assert 'mktemp -d "$DATA_DIR/.update-rollback.' not in script
    assert '"ROLLBACK_FAILED"' in script
    assert 'wait_for_health "$old_version" "" "false"' in script
    for artifact in (
        "backend.env",
        "qingjuan-backend.service",
        "qingjuan-updater.service",
        "qingjuan-updater.path",
        "qingjuan-info",
        "qingjuan-password",
        "qingjuan-uninstall",
        "qingjuan-update-runner",
    ):
        assert "backup_artifact " in script and f'"{artifact}"' in script


def test_runner_validates_and_consumes_untrusted_request() -> None:
    runner = _read("qingjuan-update-runner.sh")

    assert "O_NOFOLLOW" in runner
    assert "metadata.st_uid != expected_uid" in runner
    assert "metadata.st_nlink != 1" in runner
    assert "os.unlink(name, dir_fd=directory_descriptor)" in runner
    assert "os.fchown(temporary_descriptor" in runner
    assert "os.chown(temporary" not in runner
    assert "UPDATE_REQUEST_INVALID" in runner
    assert "UPDATE_ROLLED_BACK" in runner
    assert "ROLLBACK_FAILED" in runner


def test_root_database_backup_uses_nofollow_file_descriptors() -> None:
    script = _read("update.sh")

    assert 'getattr(os, "O_NOFOLLOW", 0)' in script
    assert "metadata.st_uid != expected_uid" in script
    assert "os.fchown(target_descriptor" in script
    assert "database backup failed integrity check" in script


def test_systemd_units_use_release_and_root_owned_state() -> None:
    backend_unit = _read("qingjuan-backend.service")
    updater_unit = _read("qingjuan-updater.service")

    assert "WorkingDirectory=/opt/qingjuan/current/app/python-backend" in backend_unit
    assert "ExecStart=/opt/qingjuan/current/venv/bin/python" in backend_unit
    assert "StateDirectory=qingjuan-updater" in updater_unit
    assert "StateDirectoryMode=0700" in updater_unit
    assert "ProtectSystem=strict" in updater_unit
    assert "ReadWritePaths=/opt/qingjuan" in updater_unit


def test_two_factor_key_is_stable_across_install_update_and_non_purge_uninstall() -> None:
    install = _read("install.sh")
    update = _read("update.sh")
    uninstall = _read("uninstall.sh")

    assert "QINGJUAN_2FA_ENCRYPTION_KEY" in install
    assert 'two_factor_encryption_key_present="true"' in install
    assert "现有 QINGJUAN_2FA_ENCRYPTION_KEY 格式无效" in install
    assert "QINGJUAN_2FA_ENCRYPTION_KEY" in update
    assert "现有 QINGJUAN_2FA_ENCRYPTION_KEY 格式无效" in update
    assert 'set_backend_value "QINGJUAN_2FA_ENCRYPTION_KEY"' in update
    assert uninstall.count('remove_tree "$CONFIG_DIR"') == 1
    assert uninstall.index('if [[ "$purge_data" == "true" ]]') < uninstall.index('remove_tree "$CONFIG_DIR"')
    assert "/etc/qingjuan" in uninstall


def test_health_revision_reads_release_marker(monkeypatch, tmp_path: Path) -> None:
    from app import main

    release_root = tmp_path / "release"
    fake_module = release_root / "app" / "python-backend" / "app" / "main.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()
    revision = "a" * 40
    (release_root / "REVISION").write_text(f"{revision}\n", encoding="utf-8")
    monkeypatch.setattr(main, "__file__", str(fake_module))

    assert main._release_revision() == revision

    (release_root / "REVISION").write_text("not-a-revision\n", encoding="utf-8")
    assert main._release_revision() == ""
