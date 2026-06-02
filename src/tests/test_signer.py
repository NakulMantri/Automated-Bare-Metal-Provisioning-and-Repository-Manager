import pytest
from pathlib import Path
from repo_manager.signer import RPMSigner


@pytest.fixture
def temp_workspace(tmp_path):
    (tmp_path / "repo" / "x86_64").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_setup_signing_keys_simulated(temp_workspace):
    signer = RPMSigner(workspace_dir=str(temp_workspace), key_name="test-key")
    key_name = signer.setup_signing_keys(simulation=True)

    assert key_name == "test-key"
    pubkey = temp_workspace / "repo" / "RPM-GPG-KEY-test-key"
    assert pubkey.exists()

    with open(pubkey, "r") as f:
        content = f.read()
        assert "BEGIN PGP PUBLIC KEY BLOCK" in content
        assert "Mock GPG key for test-key" in content


def test_sign_rpm_simulated(temp_workspace):
    signer = RPMSigner(workspace_dir=str(temp_workspace), key_name="test-key")

    # Create a mock rpm file to sign
    rpm_path = temp_workspace / "repo" / "x86_64" / "test-pkg-1.0.0-1.x86_64.rpm"
    with open(rpm_path, "w") as f:
        f.write("MOCK RPM DATA\n")

    success = signer.sign_rpm(str(rpm_path), simulation=True)
    assert success is True

    # Check if signature was appended
    with open(rpm_path, "r") as f:
        content = f.read()
        assert "SIGNATURE BLOCK" in content
        assert "Key: test-key" in content
        assert "Status: Verified" in content
