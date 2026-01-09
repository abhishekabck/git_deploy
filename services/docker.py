import subprocess
from models import AppModel
from pathlib import Path
import logging

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


def docker_build(app_model: AppModel, app_dir: Path):
    image_name = f"app_{app_model.id}_image"
    logger.info("Starting docker build process for app_id: %s, image_name: %s", app_model.id, image_name)
    
    # Validation
    dockerfile_path = Path(app_dir) / "Dockerfile"
    logger.debug("Checking for Dockerfile at: %s", dockerfile_path)
    if not dockerfile_path.is_file():
        logger.error("Dockerfile not found in %s", app_dir)
        raise FileNotFoundError("Docker file does not exists.")

    # checking if Image exists or not
    logger.debug("Checking for image: %s", image_name)
    if docker_image_exists(image_name):
        logger.info("Image: \"%s\" already Exists.", image_name)
        logger.info("Checking for container to avoid conflicts..")
        try:
            container_id = docker_container_exists(f"app_{app_model.id}_container")
            if container_id:
                logger.info("Docker Container with cid %s found!", container_id)
                logger.info("Removing Existing Container.")
                docker_remove_container(f"app_{app_model.id}_container", container_id)
                logger.info("Container Removed Successfully!")
        except Exception as e:
            raise RuntimeError(str(e))
        logger.info("Removing old image with name: %s", image_name)
        result = subprocess.run(
            ["docker", "rmi", f"{image_name}:latest"],
            cwd=app_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error("Failed! to remove Existing Docker image - %s:latest", image_name)
            raise RuntimeError("Failed! to remove Existing docker image.")
        logger.info("Existing Docker image successfully Removed!")
    logger.info("No Existing Docker image Found with conflicting name - %s:latest", image_name)
    logger.info("Executing docker build command for %s", image_name)
    process = subprocess.Popen(
        ["docker", "build", "--progress=plain", "-t", f"{image_name}", "."],
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
        raise RuntimeError("Docker build failed")
    
    logger.info("Docker build completed successfully for %s", image_name)

def docker_run(app_model: AppModel, app_dir: Path):
    logger.info("#"*40)
    image_name = f"app_{app_model.id}_image"
    container_name=f"app_{app_model.id}_container"

    logger.info(f"Checking image: {image_name}")
    if not docker_image_exists(image_name):
        logger.error("Docker image - %s:latest not found!", image_name)
        raise FileNotFoundError("Docker image does not Exists!")
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
        raise RuntimeError(e)
    #verification phase completed


    # Initiating docker Container Running command
    logger.info("Initiating Docker run from image.")
    result = subprocess.run(
        ["docker", "run", "-d", "--name", container_name, "-p", f"{app_model.internal_port}:{app_model.container_port}", f"{image_name}:latest"],
        cwd=app_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.error("Container Failed to Run with error %s", result.stderr)
        raise RuntimeError("Failed to start Docker Image.")
    logger.info("Successfully Initiated docker container with container id: %s", result.stdout.rstrip())
