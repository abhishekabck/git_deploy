import logging
import subprocess
import time
from pathlib import Path
from app.models import AppModel
from app.Errors import (DockerRunError,
                        DockerBuildError,
                        DockerfileNotFoundError,
                        DockerImageRemovalError,
                        DockerImageNotFoundError,
                        DockerContainerRemovalError,
                        )
from app.services.deploy import switch_to_branch
from app.services.docker_command_builder import DockerCommandBuilder


logger = logging.getLogger(__name__)

# add docker image command: docker build -t app_17_image .
# remove docker command: docker rm -f app_17_container

def docker_image_exists(image_name: str, tag: str = "latest") -> bool:
    try:
        # Run docker images -q <image_name>:<tag>
        result = subprocess.run(
            ["docker", "images", "-q", f"{image_name}:{tag}"],
            capture_output=True,
            text=True,
            check=True
        )
        # If output is non-empty, image exists
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        # Command failed (e.g., Docker not running)
        return False

def docker_container_exists(container_name: str, running_only: bool = False) -> str:
    try:
        cmd = ["docker", "ps", "-q", "-f", f"name={container_name}"]
        if not running_only:
            cmd.insert(2, "-a")  # add -a for all containers

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""

def docker_remove_image(image_name: str):
    try:
        # Get all image IDs for this name across all tags
        result = subprocess.run(
            ["docker", "images", "-q", image_name],
            capture_output=True,
            text=True,
            check=True
        )
        image_ids = [i for i in result.stdout.strip().split("\n") if i]
        if not image_ids:
            logger.info("Image '%s' does not exist, skipping removal.", image_name)
            return
        rm_result = subprocess.run(
            ["docker", "rmi", "-f"] + image_ids,
            capture_output=True,
            text=True
        )
        if rm_result.returncode == 0:
            logger.info("Image '%s' and all its tags removed successfully.", image_name)
        else:
            logger.error("Failed to remove image '%s': %s", image_name, rm_result.stderr.strip())
            raise DockerImageRemovalError(context=image_name)
    except DockerImageRemovalError:
        raise
    except subprocess.CalledProcessError as e:
        logger.error("Error querying image '%s': %s", image_name, e)
        raise DockerImageRemovalError(context=image_name)


def docker_remove_container(container_name: str, container_id: str):
    try:
        if container_id:
            # Remove the container (force stops if running)
            rm_result = subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True,
                text=True
            )
            if rm_result.returncode == 0:
                logger.info(f"Container '{container_name}' removed successfully.")
            else:
                logger.error(f"Error removing container: {rm_result.stderr.strip()}")
        else:
            logger.error(f"Container '{container_name}' does not exist.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking container: {e}")


def docker_build(app_model: AppModel, app_dir: Path, **kwargs):
    version_tag = str(int(time.time()))
    image_name = f"app_{app_model.id}_image"
    tagged_image = f"{image_name}:{version_tag}"
    latest_image = f"{image_name}:latest"

    logger.info("Starting docker build process for app_id: %s, image_name: %s", app_model.id, image_name)
    switch_to_branch(branch=app_model.branch, app_dir=app_dir)
    logger.info("Switched to branch: %s", app_model.branch)

    # Validation
    dockerfile_path = app_dir / Path(app_model.dockerfile_path)
    logger.debug("Checking for Dockerfile at: %s", dockerfile_path)
    if not dockerfile_path.is_file():
        logger.error("Dockerfile not found in %s", app_dir)
        raise DockerfileNotFoundError(context=str(dockerfile_path))

    logger.info("Executing docker build command for %s", image_name)
    builder = DockerCommandBuilder()
    build_cmd = (
        builder
        .build(build_context_path=app_model.build_path)
        .pull_latest_base_image(should_pull=kwargs.get("pull_latest", False))
        .with_tag(tagged_image)
        .with_tag(latest_image)
        .with_label("app_id", str(app_model.id))
        .with_label("branch", app_model.branch)
        .with_label("build_timestamp", version_tag)
        .with_progress("plain")
        .with_dockerfile(dockerfile_path)
        .without_cache(no_cache=kwargs.get("clear_cache", False))
        )
    if kwargs.get('build_args'):
        for key, value in kwargs['build_args'].items():
            build_cmd = build_cmd.with_build_arg(key, value)

    process = subprocess.Popen(
        args = build_cmd.compile(),
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # streaming live logs
    for line in process.stdout:
        logger.info(line.rstrip())

    exit_code = process.wait()

    if exit_code != 0:
        logger.error("Docker build failed for %s with exit code %s", image_name, exit_code)
        raise DockerBuildError(context=f"Docker build failed with exit code {exit_code}")
    
    logger.info("Docker build completed successfully for %s", image_name)


def docker_run(app_model: AppModel, app_dir: Path, **kwargs):
    image_name = f"app_{app_model.id}_image"
    container_name = f"app_{app_model.id}_container"

    # Allows falling back to a specific tag if provided, otherwise uses 'latest'
    target_tag = kwargs.get("tag", "latest")
    full_image_target = f"{image_name}:{target_tag}"

    logger.info(f"Checking image: {full_image_target}")
    if not docker_image_exists(image_name):
        logger.error("Docker image - %s not found!", full_image_target)
        raise DockerImageNotFoundError(context=str(full_image_target))
    logger.info("Required Image Exists!")

    logger.info("Checking if Container Exists!")
    try:
        container_id = docker_container_exists(container_name)
        if container_id:
            logger.info(f"Container {container_name} with Container_id {container_id} Found.")
            logger.info(f"Removing Container {container_name}")
            docker_remove_container(container_name, container_id)
            logger.info("Successfully removed Docker Container.")
    except Exception as e:
        logger.error(e)
        raise DockerContainerRemovalError(context=str(e))
    # verification phase completed

    # --- Constructing the command using the Builder ---
    logger.info("Constructing Docker run command.")
    builder = DockerCommandBuilder()

    run_cmd = (
        builder.run()
        .detached(is_detached=True)
        .with_name(container_name)
        .with_port_mapping(app_model.internal_port, app_model.container_port)
        .with_restart_policy(kwargs.get("restart_policy", "unless-stopped"))
        .with_resource_limits(
            memory=kwargs.get("memory", '512m'),
            cpus=kwargs.get("cpus", '1.0')
        )
        .with_log_config(
            max_size=kwargs.get("log_max_size", "10m"),
            max_file=kwargs.get("log_max_file", "3")
        )
    )

    # Injecting environment variables dynamically if provided
    if kwargs.get('env_vars'):
        for key, value in kwargs['env_vars'].items():
            run_cmd = run_cmd.with_env(key, value)

    # The image MUST be the last configuration before compile()
    run_cmd = run_cmd.with_image(full_image_target)
    # --------------------------------------------------

    # Initiating docker Container Running command
    logger.info("Initiating Docker run from image: %s", full_image_target)
    result = subprocess.run(
        args=run_cmd.compile(),
        cwd=app_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error("Container Failed to Run with error %s", result.stderr)
        raise DockerRunError(context=f"{result.stderr}")

    logger.info("Successfully Initiated docker container with container id: %s", result.stdout.rstrip())