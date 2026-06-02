import os
import time
import shutil
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import (
    FastAPI,
    Request,
    UploadFile,
    File,
    Form,
    HTTPException,
    BackgroundTasks,
)
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Initialize logger
logger = logging.getLogger("repo_manager.api")

from repo_manager.builder import RPMBuilder
from repo_manager.signer import RPMSigner
from repo_manager.publisher import RPMPublisher

app = FastAPI(
    title="Automated Bare-Metal Provisioning & Repository Manager API", version="1.0.0"
)

# Load workspace from environment or default to current working directory
WORKSPACE = Path(os.environ.get("REPO_MANAGER_WORKSPACE", os.getcwd())).resolve()
REPO_DIR = WORKSPACE / "repo"
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Ensure repo folder exists
REPO_DIR.mkdir(parents=True, exist_ok=True)

# Mount the static repository files (RPMs, repodata, and GPG keys) to /repo
app.mount("/repo", StaticFiles(directory=str(REPO_DIR)), name="repo")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Build and provisioning logs mock queues for visualization
build_jobs = []
provision_logs = [
    {
        "timestamp": "2026-06-02T20:00:01Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "PXE DHCP request received from MAC 52:54:00:fa:19:bc",
    },
    {
        "timestamp": "2026-06-02T20:00:03Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "IP assigned: 10.0.10.11",
    },
    {
        "timestamp": "2026-06-02T20:00:05Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Booting Rocky Linux 9 installer kernel over TFTP...",
    },
    {
        "timestamp": "2026-06-02T20:00:15Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Kickstart file fetched from http://10.0.10.50:8000/kickstart.ks",
    },
    {
        "timestamp": "2026-06-02T20:00:30Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Partitioning local drive /dev/sda (RAID-1 mirror setup)...",
    },
    {
        "timestamp": "2026-06-02T20:01:45Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Installing base OS packages (482/1045)...",
    },
    {
        "timestamp": "2026-06-02T20:03:12Z",
        "node": "server01.infra.local",
        "level": "SUCCESS",
        "message": "Baseline installation complete. Rebooting server...",
    },
    {
        "timestamp": "2026-06-02T20:03:40Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "SSH daemon responsive. Initializing connection...",
    },
    {
        "timestamp": "2026-06-02T20:03:45Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Ansible playbook execution started: site.yml",
    },
    {
        "timestamp": "2026-06-02T20:04:10Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Role baseline: NTP servers set, baseline packages installed.",
    },
    {
        "timestamp": "2026-06-02T20:04:30Z",
        "node": "server01.infra.local",
        "level": "WARNING",
        "message": "Role security: Disabling SSH root password logins. SSH private keys only.",
    },
    {
        "timestamp": "2026-06-02T20:04:55Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Role repo_client: Deploying repository configuration pointing to http://10.0.10.50:8000/repo/x86_64",
    },
    {
        "timestamp": "2026-06-02T20:05:10Z",
        "node": "server01.infra.local",
        "level": "INFO",
        "message": "Role repo_client: GPG signing key imported successfully.",
    },
    {
        "timestamp": "2026-06-02T20:05:25Z",
        "node": "server01.infra.local",
        "level": "SUCCESS",
        "message": "Ansible playbook executed successfully. System is COMPLIANT and PROVISIONED.",
    },
]


# Background tasks helper
def process_build(spec_content: str, filename: str, job_id: str, sim: bool):
    build_dir = WORKSPACE / "rpmbuild" / "SPECS"
    build_dir.mkdir(parents=True, exist_ok=True)
    spec_path = build_dir / filename

    # Save spec file
    with open(spec_path, "w") as f:
        f.write(spec_content)

    builder = RPMBuilder(workspace_dir=str(WORKSPACE))
    signer = RPMSigner(workspace_dir=str(WORKSPACE))
    publisher = RPMPublisher(workspace_dir=str(WORKSPACE))

    # Update job status
    job = next((j for j in build_jobs if j["id"] == job_id), None)

    try:
        if job:
            job["status"] = "Compiling"
            job["log"].append("Starting RPM build execution...")

        built_rpm = builder.build_from_spec(spec_path, simulation=sim)

        if job:
            job["status"] = "Signing"
            job["log"].append(f"RPM compiled at: {Path(built_rpm).name}")
            job["log"].append("Initiating GPG signing...")

        signer.sign_rpm(built_rpm, simulation=sim)

        if job:
            job["status"] = "Publishing"
            job["log"].append("GPG signature successfully applied.")
            job["log"].append("Updating repository index catalogs...")

        publisher.publish_and_update(built_rpm, simulation=sim)

        if job:
            job["status"] = "Completed"
            job["log"].append("Repository catalog update complete. Package is live.")
            job["rpm_name"] = Path(built_rpm).name

    except Exception as e:
        logger.error(f"Async build job {job_id} failed: {e}")
        if job:
            job["status"] = "Failed"
            job["log"].append(f"CRITICAL ERROR: {str(e)}")
    finally:
        # Cleanup uploaded spec file
        if spec_path.exists():
            spec_path.unlink()


@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    """Serve the dashboard interface."""
    try:
        # Newer Starlette signature: TemplateResponse(request, name, context)
        return templates.TemplateResponse(request, "index.html", {})
    except TypeError:
        # Older Starlette signature: TemplateResponse(name, context)
        return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/status")
def get_status():
    """Retrieve repository package metrics and active keys details."""
    rpm_dir = REPO_DIR / "x86_64"
    rpms = list(rpm_dir.glob("*.rpm")) if rpm_dir.exists() else []

    package_list = []
    for r in rpms:
        stat = r.stat()
        # Parse version and release from filename: name-version-release.arch.rpm
        stem_parts = r.stem.split("-")
        if len(stem_parts) >= 3:
            rel_arch = stem_parts[-1]
            rel = rel_arch.split(".")[0]
            ver = stem_parts[-2]
            name = "-".join(stem_parts[:-2])
        else:
            name = stem_parts[0] if stem_parts else "custom-package"
            ver = "1.0.0"
            rel = "1"

        # Read mock signature verification from mock/file footer
        signed = False
        if r.exists():
            try:
                with open(r, "rb") as f:
                    # Seek to end to see if we appended our mock signature block
                    f.seek(max(0, stat.st_size - 200))
                    content = f.read().decode("utf-8", errors="ignore")
                    if "SIGNATURE BLOCK" in content or "verified" in content.lower():
                        signed = True
            except:
                pass

        package_list.append(
            {
                "name": name,
                "version": f"{ver}-{rel}",
                "filename": r.name,
                "size": f"{stat.st_size / 1024:.2f} KB",
                "modified": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)
                ),
                "signed": signed
                or not r.name.startswith("unsigned"),  # Mocked packages
            }
        )

    gpg_key_exists = any(REPO_DIR.glob("RPM-GPG-KEY-*"))
    gpg_key_name = ""
    if gpg_key_exists:
        key_file = list(REPO_DIR.glob("RPM-GPG-KEY-*"))[0]
        gpg_key_name = key_file.name.replace("RPM-GPG-KEY-", "")

    return {
        "workspace": str(WORKSPACE),
        "total_packages": len(package_list),
        "gpg_key_configured": gpg_key_exists,
        "gpg_key_name": gpg_key_name,
        "packages": package_list,
        "repo_url": f"http://10.0.10.50:8000/repo/x86_64",
        "last_update": (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) if rpms else "Never"
        ),
    }


@app.post("/api/compile")
def compile_rpm(
    background_tasks: BackgroundTasks,
    spec_file: UploadFile = File(...),
    sim: bool = Form(True),
):
    """Trigger an RPM compilation, GPG sign, and publishing in background."""
    if not spec_file.filename.endswith(".spec"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only RPM SPEC files are allowed.",
        )

    job_id = f"job-{int(time.time())}"
    spec_content = spec_file.file.read().decode("utf-8")

    # Store build job info
    build_jobs.append(
        {
            "id": job_id,
            "filename": spec_file.filename,
            "status": "Queued",
            "timestamp": time.strftime("%H:%M:%S"),
            "log": ["Job queued in build scheduler."],
            "rpm_name": "",
        }
    )

    # Run the process in the background
    background_tasks.add_task(
        process_build, spec_content, spec_file.filename, job_id, sim
    )

    return {"message": "Compilation task accepted in background.", "job_id": job_id}


@app.get("/api/builds")
def get_build_jobs():
    """Retrieve build jobs history and active queues status."""
    return build_jobs


@app.get("/api/provision-logs")
def get_provision_logs():
    """Retrieve logs simulating PXE boot & Ansible playbooks execution."""
    return provision_logs


@app.post("/api/provision-logs/clear")
def clear_provision_logs():
    """Reset provisioning logs."""
    provision_logs.clear()
    return {"status": "cleared"}


@app.post("/api/provision-logs/trigger")
def trigger_provision(node_name: str = Form("server04.infra.local")):
    """Triggers a new simulated provisioning thread log."""
    new_logs = [
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"PXE DHCP request received from MAC 52:54:00:a1:bb:{int(time.time())%100:02d}",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"IP assigned: 10.0.10.{100 + len(provision_logs)//2}",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"Booting target installation over TFTP PXE...",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"Fetched Kickstart automation payload...",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"Applying Anaconda system partitioning and storage allocation...",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "SUCCESS",
            "message": f"Base configuration complete. Rebooting into target kernel...",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "INFO",
            "message": f"Triggering local configuration management pipeline via Ansible playbooks...",
        },
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "node": node_name,
            "level": "SUCCESS",
            "message": f"Provisioning and compliance checks successful. Host {node_name} is active.",
        },
    ]

    # We can extend the logs in the background or just append them directly for simulation
    # Let's append them to the session log
    for log in new_logs:
        provision_logs.append(log)

    return {"status": "triggered", "node": node_name}
