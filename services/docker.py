import subprocess
from models import AppModel
from pathlib import Path


# add docker image command: docker build -t app_17_image .
# remove docker command: docker rm -f app_17_container

def docker_build(app_model: AppModel, app_dir):
    image_name = Path(f"app_{app_model.id}_image")
    # Validation
    dockerfile_path = Path(app_dir) / "Dockerfile"
    if not dockerfile_path.is_file():
        raise FileNotFoundError("Docker file does not exists.")

    # checking if Image exists or not
    image_file_path = Path(app_dir) / image_name / ".tar"
    if image_file_path.is_file():
        result = subprocess.run(
            ["rm", image_name / ".tar"],
            cwd = app_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr))

    result = subprocess.run(
        ["docker", "build", "-t", f"{image_name}", "."],
        cwd=app_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

def docker_run():
    pass