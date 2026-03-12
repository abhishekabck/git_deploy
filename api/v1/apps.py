import logging
import shutil
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as ApiPath
from sqlalchemy.orm import Session
from typing import Annotated, List
from starlette import status
from pathlib import Path

from app.dependencies import get_db
from app.models import AppModel
from app.models.users import Users
from app.constants import AppStatus
from app.services.auth import get_current_user
from app.services.deploy import validate_github_repo, clone_or_pull_repo
from app.services.docker import (
    docker_build, docker_run, docker_container_exists,
    docker_remove_container, docker_remove_image,
)
from app.services.port_manager import allocate_free_port
from app.schemas import AppCreateRequestModel, AppResponseModel, AppListItem, AppDetail, AppDeployRequestModel
from app.Errors import AppNotFoundError
from app.config import Config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apps")

BASE_APPS_DIR = Path(Config.BASE_APPS_DIR)
BASE_APPS_DIR.mkdir(parents=True, exist_ok=True)

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[Users, Depends(get_current_user)]


def _get_owned_app(app_id: int, user: Users, db: Session) -> AppModel:
    """Fetch an app and verify it belongs to the current user."""
    app = db.query(AppModel).filter(AppModel.id == app_id).first()
    if app is None:
        raise AppNotFoundError(detail="App not found")
    if app.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return app


@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=AppResponseModel)
def create_app(model: AppCreateRequestModel, db: db_dependency, current_user: user_dependency):
    logger.info("App Create Request for repo: %s by user_id=%s", model.repo_url, current_user.id)

    validate_github_repo(model.repo_url)

    new_app = AppModel(
        name=model.name,
        repo_url=model.repo_url,
        container_port=model.container_port,
        branch=model.branch,
        build_path=model.source_dir,
        dockerfile_path=model.dockerfile_path,
        env=model.env,
        user_id=current_user.id,
    )
    db.add(new_app)
    db.flush()  # attach id without committing

    new_app.subdomain = f"app-{new_app.id}"
    db.commit()
    logger.info("Created app %s for user_id=%s", new_app.id, current_user.id)

    return {
        "id": new_app.id,
        "subdomain": new_app.subdomain,
        "container_port": new_app.container_port,
        "status": new_app.status.value,
    }


@router.get("/list/", status_code=status.HTTP_200_OK, response_model=List[AppListItem])
def get_apps(
    db: db_dependency,
    current_user: user_dependency,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
):
    logger.info("Listing apps for user_id=%s status=%s page=%d size=%d", current_user.id, status, page, size)

    query = db.query(AppModel).filter(AppModel.user_id == current_user.id)
    if status and status in [s.value for s in AppStatus]:
        query = query.filter(AppModel.status == status)

    apps = query.offset((page - 1) * size).limit(size).all()
    logger.debug("Found %d apps for user_id=%s", len(apps), current_user.id)

    return [
        {
            "id": app.id,
            "name": app.name,
            "subdomain": app.subdomain,
            "container_port": app.container_port,
            "repo_url": app.repo_url,
            "build_path": app.build_path,
            "branch": app.branch,
            "status": app.status.value,
        }
        for app in apps
    ]


@router.get("/{app_id}", status_code=status.HTTP_200_OK, response_model=AppDetail)
def get_app(db: db_dependency, current_user: user_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Fetching details for app_id=%s user_id=%s", app_id, current_user.id)
    app = _get_owned_app(app_id, current_user, db)

    return {
        "id": app.id,
        "name": app.name,
        "repo_url": app.repo_url,
        "subdomain": app.subdomain,
        "internal_port": app.internal_port,
        "container_port": app.container_port,
        "branch": app.branch,
        "build_path": app.build_path,
        "dockerfile_path": app.dockerfile_path,
        "status": app.status.value,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
        "env": app.env,
    }


@router.delete("/delete/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_app(db: db_dependency, current_user: user_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Delete request for app_id=%s user_id=%s", app_id, current_user.id)
    app = _get_owned_app(app_id, current_user, db)

    image_name = f"app_{app_id}_image"
    container_name = f"app_{app_id}_container"

    container_id = docker_container_exists(container_name)
    if container_id:
        docker_remove_container(container_name, container_id)
        logger.info("Container %s removed.", container_name)

    docker_remove_image(image_name)

    app_dir = BASE_APPS_DIR / f"app-{app_id}"
    log_dir = Config.BASE_LOGS_DIR / f"app-{app_id}"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    if log_dir.exists():
        shutil.rmtree(log_dir)

    db.delete(app)
    db.commit()
    logger.info("App %s deleted.", app_id)


@router.post("/{app_id}/deploy", status_code=status.HTTP_201_CREATED)
def deploy_app(
    props: AppDeployRequestModel,
    db: db_dependency,
    current_user: user_dependency,
    app_id: int = ApiPath(gt=0),
):
    logger.info("Deploy triggered for app_id=%s user_id=%s", app_id, current_user.id)
    app = _get_owned_app(app_id, current_user, db)

    if props.branch is not None:
        app.branch = props.branch
    if props.dockerfile_path is not None:
        app.dockerfile_path = props.dockerfile_path
    if props.source_dir is not None:
        app.build_path = props.source_dir
    if props.env is not None:
        app.env = props.env

    app_dir = BASE_APPS_DIR / f"app-{app.id}"
    if props.force_rebuild and app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)

    try:
        clone_or_pull_repo(str(app.repo_url), app_dir)
        logger.info("Code fetched for app %s", app_id)
        app.status = AppStatus.PREPARED
        db.commit()

        docker_build(app, app_dir, build_args=props.build_args or {}, clear_cache=props.clear_cache or False)
        logger.info("Docker build successful for app %s", app_id)

        container_name = f"app_{app.id}_container"
        container_id = docker_container_exists(container_name)
        if container_id:
            docker_remove_container(container_name, container_id)
            app.internal_port = None
            db.commit()

        app.internal_port = allocate_free_port(db)
        db.commit()
        logger.info("Port %d allocated for app %s", app.internal_port, app_id)

        Config.BASE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        docker_run(app, app_dir, env_vars=props.env or {})
        app.status = AppStatus.RUNNING
        db.commit()
        logger.info("App %s is RUNNING on port %d", app_id, app.internal_port)

    except Exception as e:
        logger.error("Deployment failed for app %s: %s", app_id, str(e))
        app.status = AppStatus.ERROR
        db.commit()
        raise

    return {"id": app.id, "status": app.status.value}
