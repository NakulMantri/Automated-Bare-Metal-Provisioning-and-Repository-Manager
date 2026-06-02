import os
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger("repo_manager.builder")


class RPMBuilder:
    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = Path(workspace_dir or os.getcwd()).resolve()
        self.build_dir = self.workspace_dir / "rpmbuild"
        self.output_dir = self.workspace_dir / "repo" / "x86_64"

        # Ensure directories exist
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _is_docker_available(self) -> bool:
        """Check if Docker CLI is installed and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def build_from_spec(self, spec_path: str, simulation: bool = False) -> str:
        """
        Compiles an RPM package from a SPEC file.
        Returns the path of the built RPM package.
        """
        spec_path = Path(spec_path).resolve()
        if not spec_path.exists():
            raise FileNotFoundError(f"SPEC file not found: {spec_path}")

        # Parse SPEC file basic details for logging/naming (Name, Version, Release)
        pkg_info = self._parse_spec(spec_path)
        rpm_filename = (
            f"{pkg_info['name']}-{pkg_info['version']}-{pkg_info['release']}.x86_64.rpm"
        )
        dest_rpm_path = self.output_dir / rpm_filename

        if simulation or not self._is_docker_available():
            logger.warning(
                "Docker not available or simulation mode active. Running simulated RPM compilation."
            )
            return self._simulate_build(pkg_info, dest_rpm_path)

        return self._build_containerized(spec_path, pkg_info, dest_rpm_path)

    def _parse_spec(self, spec_path: Path) -> dict:
        """Extract Name, Version, and Release from a SPEC file."""
        info = {"name": "custom-pkg", "version": "1.0.0", "release": "1"}
        try:
            with open(spec_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Name:"):
                        info["name"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:"):
                        info["version"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Release:"):
                        # Handle macro replacements if any, keep it simple
                        release_val = line.split(":", 1)[1].strip()
                        info["release"] = release_val.split("%")[0].strip()
        except Exception as e:
            logger.error(f"Error parsing SPEC file: {e}")
        return info

    def _simulate_build(self, pkg_info: dict, dest_path: Path) -> str:
        """Create a mock/empty RPM file to simulate compilation on non-RPM systems."""
        logger.info(
            f"Simulating build steps for: {pkg_info['name']} v{pkg_info['version']}"
        )
        logger.info("Step 1/4: Unpacking source files...")
        logger.info("Step 2/4: Executing %build section (make, configure)...")
        logger.info("Step 3/4: Executing %install section (destdir copy)...")
        logger.info("Step 4/4: Package assembly via rpmbuild...")

        # Write dummy binary content representing a mock RPM
        with open(dest_path, "w") as f:
            f.write(
                f"MOCK-RPM-BINARY\nName: {pkg_info['name']}\nVersion: {pkg_info['version']}\nRelease: {pkg_info['release']}\nArchitecture: x86_64\n"
            )

        logger.info(f"Simulated RPM package built successfully: {dest_path}")
        return str(dest_path)

    def _build_containerized(
        self, spec_path: Path, pkg_info: dict, dest_path: Path
    ) -> str:
        """Compile the RPM inside a RHEL/Rocky Linux container environment."""
        logger.info(
            f"Starting containerized RPM build for {pkg_info['name']} in Rocky Linux 9"
        )

        # Build RPM building environment if not already built
        dockerfile_path = self.workspace_dir / "scripts" / "Dockerfile.builder"
        if not dockerfile_path.exists():
            raise FileNotFoundError(
                f"Dockerfile.builder not found at {dockerfile_path}"
            )

        # Compile builder image
        logger.info("Verifying build container image 'rpm-builder-local'...")
        subprocess.run(
            [
                "docker",
                "build",
                "-t",
                "rpm-builder-local",
                "-f",
                str(dockerfile_path),
                str(self.workspace_dir / "scripts"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        # Setup container bind mounts and execute rpmbuild inside container
        # Mount the workspace so docker can write the built RPM directly to the output folder
        # We copy the SPEC to a temporary location inside workspace
        docker_spec_dir = self.workspace_dir / "rpmbuild" / "SPECS"
        docker_spec_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(spec_path, docker_spec_dir / spec_path.name)

        logger.info("Executing rpmbuild within container...")
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.workspace_dir}:/workspace",
            "rpm-builder-local",
            "rpmbuild",
            "-bb",
            f"/workspace/rpmbuild/SPECS/{spec_path.name}",
            "--define",
            "_topdir /workspace/rpmbuild",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(
                f"RPM build failed:\nStdout: {result.stdout}\nStderr: {result.stderr}"
            )
            raise RuntimeError(f"RPM container compilation failed: {result.stderr}")

        # Find compiled RPM in rpmbuild/RPMS/x86_64/ or similar and move it to repo directory
        container_built_rpms = list(
            (self.workspace_dir / "rpmbuild" / "RPMS").glob("**/*.rpm")
        )
        if not container_built_rpms:
            raise RuntimeError(
                "RPM was compiled but not found in the output directory structure."
            )

        built_rpm = container_built_rpms[0]
        shutil.move(str(built_rpm), str(dest_path))

        # Cleanup container output dirs
        shutil.rmtree(self.workspace_dir / "rpmbuild" / "RPMS", ignore_errors=True)
        shutil.rmtree(self.workspace_dir / "rpmbuild" / "BUILD", ignore_errors=True)
        shutil.rmtree(self.workspace_dir / "rpmbuild" / "BUILDROOT", ignore_errors=True)

        logger.info(f"RPM compiled successfully in container: {dest_path}")
        return str(dest_path)
