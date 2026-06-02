import os
import subprocess
import shutil
import hashlib
import time
import gzip
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

logger = logging.getLogger("repo_manager.publisher")


class RPMPublisher:
    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = Path(workspace_dir or os.getcwd()).resolve()
        self.repo_dir = self.workspace_dir / "repo" / "x86_64"
        self.repodata_dir = self.repo_dir / "repodata"

        # Ensure directories exist
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.repodata_dir.mkdir(parents=True, exist_ok=True)

    def _is_createrepo_available(self) -> bool:
        """Check if createrepo or createrepo_c is available in the path."""
        for cmd in ["createrepo_c", "createrepo"]:
            try:
                subprocess.run(
                    [cmd, "--version"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                return True
            except FileNotFoundError:
                continue
        return False

    def publish_and_update(
        self, rpm_path: str = None, simulation: bool = False
    ) -> bool:
        """
        Moves the RPM into the repository folder (if specified) and rebuilds repository metadata.
        """
        if rpm_path:
            rpm_path = Path(rpm_path)
            if not rpm_path.exists():
                raise FileNotFoundError(
                    f"RPM file to publish does not exist: {rpm_path}"
                )

            dest_path = self.repo_dir / rpm_path.name
            if rpm_path.resolve() != dest_path.resolve():
                logger.info(
                    f"Publishing package {rpm_path.name} to repository folder..."
                )
                shutil.copy2(rpm_path, dest_path)

        # Re-index the repository
        has_createrepo = self._is_createrepo_available()

        if simulation or not has_createrepo:
            logger.warning(
                "createrepo not available or simulation active. Creating simulated repodata indexes."
            )
            return self._simulate_metadata()

        return self._run_createrepo()

    def _run_createrepo(self) -> bool:
        """Execute createrepo to generate YUM metadata indexes."""
        logger.info("Updating repository metadata database via createrepo...")

        # Determine command to run
        cmd = "createrepo_c" if shutil.which("createrepo_c") else "createrepo"
        result = subprocess.run(
            [cmd, str(self.repo_dir.parent)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.error(f"createrepo execution failed:\n{result.stderr}")
            # Try running inside Rocky Linux container
            logger.info("Attempting containerized repository indexing...")
            try:
                container_cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{self.workspace_dir}:/workspace",
                    "rpm-builder-local",
                    cmd,
                    "/workspace/repo",
                ]
                container_res = subprocess.run(
                    container_cmd, capture_output=True, text=True, check=False
                )
                if container_res.returncode == 0:
                    logger.info("Containerized repository indexing succeeded.")
                    return True
            except Exception as ex:
                logger.error(f"Containerized indexing failed: {ex}")
            return False

        logger.info("Repository metadata rebuilt successfully.")
        return True

    def _simulate_metadata(self) -> bool:
        """Generate mock XML repodata structures for client simulator download."""
        logger.info(
            "Generating mock repomd.xml, primary.xml.gz, and filelists.xml.gz..."
        )

        # Discover all packages currently in repo
        rpms = list(self.repo_dir.glob("*.rpm"))
        timestamp = int(time.time())

        # Register namespace prefix globally
        ET.register_namespace("rpm", "http://linux.duke.edu/metadata/rpm")

        # 1. Create simulated primary.xml file listing RPM packages
        primary_xml = self.repodata_dir / "primary.xml"

        # Construct primary XML database with proper attributes dictionary
        attribs = {
            "xmlns": "http://linux.duke.edu/metadata/common",
            "packages": str(len(rpms)),
        }
        root = ET.Element("metadata", attrib=attribs)

        for rpm in rpms:
            # Parse mock info or extract from filename: [name]-[version]-[release]
            # Standard RPM filename format: name-version-release.arch.rpm
            stem_parts = rpm.stem.split("-")
            if len(stem_parts) >= 3:
                release_arch = stem_parts[-1]
                release = release_arch.split(".")[0]
                version = stem_parts[-2]
                name = "-".join(stem_parts[:-2])
            else:
                name = stem_parts[0] if stem_parts else "custom-package"
                version = "1.0.0"
                release = "1"
            arch = "x86_64"

            package = ET.SubElement(root, "package", type="rpm")
            ET.SubElement(package, "name").text = name
            ET.SubElement(package, "arch").text = arch

            version_elem = ET.SubElement(package, "version")
            version_elem.set("epoch", "0")
            version_elem.set("ver", version)
            version_elem.set("rel", release)

            # Simulated file checksum
            file_hash = hashlib.sha256(rpm.name.encode()).hexdigest()
            checksum = ET.SubElement(package, "checksum", type="sha256", pkgid="YES")
            checksum.text = file_hash

            summary = ET.SubElement(package, "summary")
            summary.text = f"Simulated custom enterprise RPM packages for {name}"

            description = ET.SubElement(package, "description")
            description.text = f"This package contains configuration management components for bare-metal server baseline setups of {name}."

            packager = ET.SubElement(package, "packager")
            packager.text = "Infrastructure Automation Team"

            size = ET.SubElement(package, "size")
            size.set("package", str(rpm.stat().st_size if rpm.exists() else 1024))
            size.set("installed", "4096")
            size.set("archive", "2048")

            location = ET.SubElement(package, "location")
            location.set("href", f"x86_64/{rpm.name}")

            # Format/RPM metadata using URI tags
            fmt = ET.SubElement(package, "format")
            ET.SubElement(fmt, "{http://linux.duke.edu/metadata/rpm}license").text = (
                "Proprietary"
            )
            ET.SubElement(fmt, "{http://linux.duke.edu/metadata/rpm}vendor").text = (
                "Internal Enterprise LLC"
            )
            ET.SubElement(fmt, "{http://linux.duke.edu/metadata/rpm}group").text = (
                "System Environment/Base"
            )
            ET.SubElement(fmt, "{http://linux.duke.edu/metadata/rpm}buildhost").text = (
                "builder.infra.local"
            )
            ET.SubElement(fmt, "{http://linux.duke.edu/metadata/rpm}sourcerpm").text = (
                f"{name}-{version}-{release}.src.rpm"
            )

        # Write primary.xml and compress it
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)
        tree.write(primary_xml, encoding="utf-8", xml_declaration=True)

        primary_gz = self.repodata_dir / "primary.xml.gz"
        with open(primary_xml, "rb") as f_in:
            with gzip.open(primary_gz, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        primary_xml.unlink()  # Cleanup uncompressed file

        # Calculate checksums for index configuration
        primary_gz_hash = self._get_file_hash(primary_gz)

        # 2. Write main repomd.xml index file referencing primary.xml.gz
        repomd_xml = self.repodata_dir / "repomd.xml"

        repomd_root = ET.Element("repomd", xmlns="http://linux.duke.edu/metadata/repo")

        # Add primary data item
        data_primary = ET.SubElement(repomd_root, "data", type="primary")
        checksum_elem = ET.SubElement(data_primary, "checksum", type="sha256")
        checksum_elem.text = primary_gz_hash

        open_checksum = ET.SubElement(data_primary, "open-checksum", type="sha256")
        open_checksum.text = primary_gz_hash  # In simulation they can match

        location_elem = ET.SubElement(data_primary, "location")
        location_elem.set("href", "repodata/primary.xml.gz")

        timestamp_elem = ET.SubElement(data_primary, "timestamp")
        timestamp_elem.text = str(timestamp)

        size_elem = ET.SubElement(data_primary, "size")
        size_elem.text = str(primary_gz.stat().st_size)

        repomd_tree = ET.ElementTree(repomd_root)
        ET.indent(repomd_tree, space="  ", level=0)
        repomd_tree.write(repomd_xml, encoding="utf-8", xml_declaration=True)

        logger.info("Simulated repository metadata database built successfully.")
        return True

    def _get_file_hash(self, filepath: Path) -> str:
        """Calculate SHA256 of a file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
