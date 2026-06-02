import os
import sys
import click
import logging
import uvicorn
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("repo_manager.cli")

from repo_manager.builder import RPMBuilder
from repo_manager.signer import RPMSigner
from repo_manager.publisher import RPMPublisher


@click.group()
@click.option("--workspace", "-w", type=click.Path(), help="Target workspace path.")
@click.pass_context
def cli(ctx, workspace):
    """Automated Bare-Metal Provisioning & RPM Repository Manager CLI."""
    ctx.ensure_object(dict)
    ctx.obj["WORKSPACE"] = workspace or os.getcwd()


@cli.command("init")
@click.option(
    "--key-name", default="custom-internal", help="Name of GPG key to generate."
)
@click.option("--sim", is_flag=True, help="Force mock/simulated key generation.")
@click.pass_context
def init(ctx, key_name, sim):
    """Initializes the repository folders and generates GPG signing keys."""
    workspace = ctx.obj["WORKSPACE"]
    logger.info(f"Initializing repository workspace in {workspace}...")

    # Force creation of directories
    for folder in [
        "repo/x86_64",
        "rpmbuild/SPECS",
        "rpmbuild/SOURCES",
        "rpmbuild/RPMS",
    ]:
        Path(workspace, folder).mkdir(parents=True, exist_ok=True)

    signer = RPMSigner(workspace_dir=workspace, key_name=key_name)
    signer.setup_signing_keys(simulation=sim)

    publisher = RPMPublisher(workspace_dir=workspace)
    publisher.publish_and_update(simulation=sim)

    click.echo(
        click.style(
            "\n✔ Workspace and GPG environment initialized successfully!",
            fg="green",
            bold=True,
        )
    )


@cli.command("build")
@click.option(
    "--spec", required=True, type=click.Path(exists=True), help="Path to RPM SPEC file."
)
@click.option("--sim", is_flag=True, help="Force mock/simulated build.")
@click.pass_context
def build(ctx, spec, sim):
    """Compiles an RPM package from a SPEC file."""
    workspace = ctx.obj["WORKSPACE"]
    builder = RPMBuilder(workspace_dir=workspace)

    try:
        built_rpm = builder.build_from_spec(spec, simulation=sim)
        click.echo(
            click.style(
                f"\n✔ RPM successfully compiled at: {built_rpm}", fg="green", bold=True
            )
        )
    except Exception as e:
        logger.error(f"RPM build failed: {e}")
        sys.exit(1)


@cli.command("sign")
@click.option(
    "--rpm",
    required=True,
    type=click.Path(exists=True),
    help="Path to target RPM package.",
)
@click.option(
    "--key-name", default="custom-internal", help="GPG key name to sign with."
)
@click.option("--sim", is_flag=True, help="Force mock/simulated signing.")
@click.pass_context
def sign(ctx, rpm, key_name, sim):
    """Signs an RPM package using GPG key."""
    workspace = ctx.obj["WORKSPACE"]
    signer = RPMSigner(workspace_dir=workspace, key_name=key_name)

    success = signer.sign_rpm(rpm, simulation=sim)
    if success:
        click.echo(
            click.style(f"\n✔ RPM successfully signed: {rpm}", fg="green", bold=True)
        )
    else:
        click.echo(click.style("\n❌ Failed to sign RPM package.", fg="red", bold=True))
        sys.exit(1)


@cli.command("publish")
@click.option(
    "--rpm",
    type=click.Path(exists=True),
    help="Optional path to RPM to add to repository before indexing.",
)
@click.option("--sim", is_flag=True, help="Force mock/simulated metadata indexing.")
@click.pass_context
def publish(ctx, rpm, sim):
    """Regenerates repository YUM metadata indexes."""
    workspace = ctx.obj["WORKSPACE"]
    publisher = RPMPublisher(workspace_dir=workspace)

    success = publisher.publish_and_update(rpm_path=rpm, simulation=sim)
    if success:
        click.echo(
            click.style(
                "\n✔ YUM Repository indexes and metadata updated successfully!",
                fg="green",
                bold=True,
            )
        )
    else:
        click.echo(
            click.style(
                "\n❌ Failed to update repository metadata.", fg="red", bold=True
            )
        )
        sys.exit(1)


@cli.command("server")
@click.option("--host", default="0.0.0.0", help="Binding host IP.")
@click.option("--port", default=8000, help="Listening port number.")
@click.option("--reload", is_flag=True, help="Enable automatic web-server reloading.")
@click.pass_context
def server(ctx, host, port, reload):
    """Launches the FastAPI repository API and administrative dashboard."""
    workspace = ctx.obj["WORKSPACE"]
    os.environ["REPO_MANAGER_WORKSPACE"] = str(workspace)

    logger.info(f"Starting Repository Web Server on {host}:{port}...")
    uvicorn.run("repo_manager.api:app", host=host, port=port, reload=reload)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
