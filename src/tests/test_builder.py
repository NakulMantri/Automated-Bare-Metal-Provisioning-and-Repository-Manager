import pytest
from pathlib import Path
from repo_manager.builder import RPMBuilder


@pytest.fixture
def temp_workspace(tmp_path):
    """Creates a temporary workspace folder layout."""
    (tmp_path / "repo" / "x86_64").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def sample_spec(temp_workspace):
    """Creates a valid sample RPM SPEC file for parsing verification."""
    spec_content = """Name: test-app
Version: 2.3.4
Release: 1%{?dist}
Summary: Test application spec file
License: MIT
%description
A sample spec file for testing RPM compilation module.
"""
    spec_path = temp_workspace / "test-app.spec"
    with open(spec_path, "w") as f:
        f.write(spec_content)
    return spec_path


def test_parse_spec(temp_workspace, sample_spec):
    builder = RPMBuilder(workspace_dir=str(temp_workspace))
    info = builder._parse_spec(sample_spec)

    assert info["name"] == "test-app"
    assert info["version"] == "2.3.4"
    assert info["release"] == "1"


def test_simulated_build(temp_workspace, sample_spec):
    builder = RPMBuilder(workspace_dir=str(temp_workspace))

    # Run in simulation mode
    built_rpm_path = builder.build_from_spec(sample_spec, simulation=True)

    rpm_file = Path(built_rpm_path)
    assert rpm_file.exists()
    assert rpm_file.name == "test-app-2.3.4-1.x86_64.rpm"

    # Verify contents written to mock
    with open(rpm_file, "r") as f:
        content = f.read()
        assert "Name: test-app" in content
        assert "Version: 2.3.4" in content
        assert "Release: 1" in content
