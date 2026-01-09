import subprocess
from models import AppModel
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# add docker image command: docker build -t app_17_image .
# remove docker command: docker rm -f app_17_container

def docker_build(app_model: AppModel, app_dir):
    image_name = f"app_{app_model.id}_image"
    logger.info("Starting docker build process for app_id: %s, image_name: %s", app_model.id, image_name)
    
    # Validation
    dockerfile_path = Path(app_dir) / "Dockerfile"
    logger.debug("Checking for Dockerfile at: %s", dockerfile_path)
    if not dockerfile_path.is_file():
        logger.error("Dockerfile not found in %s", app_dir)
        raise FileNotFoundError("Docker file does not exists.")

    # checking if Image exists or not
    image_file_path = Path(app_dir) / f"{image_name}.tar"
    logger.debug("Checking for existing image tar at: %s", image_file_path)
    if image_file_path.is_file():
        logger.info("Existing image tar found, removing: %s", image_file_path)
        result = subprocess.run(
            ["rm", f"{image_name}.tar"],
            cwd = app_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error("Failed to remove existing image tar: %s", result.stderr)
            raise RuntimeError(str(result.stderr))

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

def docker_run():
    pass