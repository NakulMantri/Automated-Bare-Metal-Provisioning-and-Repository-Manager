import pytest
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from repo_manager.publisher import RPMPublisher


@pytest.fixture
def temp_workspace(tmp_path):
    (tmp_path / "repo" / "x86_64").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_publish_and_metadata_generation(temp_workspace):
    publisher = RPMPublisher(workspace_dir=str(temp_workspace))

    # 1. Create a mock package to publish
    rpm_source = temp_workspace / "demo-pkg-1.2.3-4.x86_64.rpm"
    with open(rpm_source, "w") as f:
        f.write("RPM BINARY BODY")

    # 2. Publish package and generate metadata
    success = publisher.publish_and_update(rpm_path=str(rpm_source), simulation=True)
    assert success is True

    # Verify package was copied
    published_rpm = temp_workspace / "repo" / "x86_64" / "demo-pkg-1.2.3-4.x86_64.rpm"
    assert published_rpm.exists()

    # Verify metadata files were created
    repomd_xml = temp_workspace / "repo" / "x86_64" / "repodata" / "repomd.xml"
    primary_gz = temp_workspace / "repo" / "x86_64" / "repodata" / "primary.xml.gz"

    assert repomd_xml.exists()
    assert primary_gz.exists()

    # 3. Verify contents of repomd.xml (points to primary.xml.gz)
    tree_md = ET.parse(repomd_xml)
    root_md = tree_md.getroot()
    # Check namespace mapping
    assert "repomd" in root_md.tag
    data_elements = root_md.findall("{http://linux.duke.edu/metadata/repo}data")
    assert len(data_elements) > 0
    assert data_elements[0].get("type") == "primary"

    # 4. Extract and verify contents of primary.xml.gz
    with gzip.open(primary_gz, "rb") as f:
        primary_content = f.read()

    root_p = ET.fromstring(primary_content)
    assert "metadata" in root_p.tag
    assert root_p.get("packages") == "1"

    package_element = root_p.find("{http://linux.duke.edu/metadata/common}package")
    assert package_element is not None
    assert (
        package_element.find("{http://linux.duke.edu/metadata/common}name").text
        == "demo-pkg"
    )

    version_elem = package_element.find(
        "{http://linux.duke.edu/metadata/common}version"
    )
    assert version_elem.get("ver") == "1.2.3"
    assert version_elem.get("rel") == "4"
