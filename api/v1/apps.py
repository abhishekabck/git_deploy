import logging
import shutil
from fastapi import APIRouter, Depends
from fastapi import Path as ApiPath
from sqlalchemy.orm import Session
from typing import Annotated, List
from starlette import status
from app.database import SessionLocal
from app.models import AppModel
from app.constants import AppStatus
from pathlib import Path
from app.services.deploy import validate_github_repo, clone_or_pull_repo
from app.services.docker import docker_build, docker_run, docker_container_exists, docker_remove_container, docker_remove_image
from app.services.port_manager import allocate_free_port
from app.schemas import AppCreateRequestModel, AppResponseModel, AppListItem, AppDetail, AppDeployRequestModel
from app.Errors import AppNotFoundError
from app.config import Config

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/apps",
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

BASE_APPS_DIR = Path(Config.BASE_APPS_DIR)
BASE_APPS_DIR.mkdir(parents=True, exist_ok=True)

# dependencies
db_dependency = Annotated[Session, Depends(get_db)]


@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=AppResponseModel)
def create_app(model: AppCreateRequestModel, db: db_dependency):
    logger.info("App Create Request for repo: %s", model.repo_url)

    validate_github_repo(model.repo_url)


    new_app = AppModel(
        name=model.name,
        repo_url=model.repo_url,
        container_port=model.container_port,
        branch=model.branch,
        build_path=model.source_dir,
        dockerfile_path=model.dockerfile_path,
        env = model.env
    )
    db.add(new_app)
    db.flush()  ## i used because it attaches id without commiting
    
    app_id = new_app.id
    new_app.subdomain = f"app-{app_id}"
    # internal_port is not assigned here — it is dynamically allocated at deploy time

    logger.info("Created app record in DB with ID: %s", app_id)
    
    db.add(new_app)
    db.commit()
    logger.info("Successfully committed app %s to database.", app_id)
    
    return {
        "id": new_app.id,
        "subdomain": new_app.subdomain,
        "container_port": new_app.container_port,
        "status": new_app.status.value
    }

@router.delete("/delete/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_app(db: db_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Delete request received for app_id: %s", app_id)
    model = db.query(AppModel).filter(AppModel.id == app_id).first()
    if model is None:
        logger.warning("App with ID %s not found.", app_id)
        raise AppNotFoundError(detail="App not found")

    image_name = f"app_{app_id}_image"
    container_name = f"app_{app_id}_container"

    # Step 1: Stop and remove the container if it exists
    container_id = docker_container_exists(container_name)
    if container_id:
        logger.info("Container %s found. Removing it.", container_name)
        docker_remove_container(container_name, container_id)
        logger.info("Container %s removed.", container_name)

    # Step 2: Remove the Docker image (all tags) if it exists
    logger.info("Removing Docker image: %s", image_name)
    docker_remove_image(image_name)

    # Step 3: Remove the app directory from filesystem
    app_dir = BASE_APPS_DIR / f"app-{app_id}"
    log_dir = Config.BASE_LOGS_DIR / f"app-{app_id}"
    if app_dir.exists():
        logger.info("Removing app directory: %s", app_dir)
        shutil.rmtree(app_dir)
        logger.info("App directory removed.")
    if log_dir.exists():
        logger.info("Removing log directory: %s", log_dir)
        shutil.rmtree(log_dir)
        logger.info("Log directory removed.")

    # Step 4: Delete the DB record
    db.delete(model)
    db.commit()
    logger.info("App %s deleted successfully from database.", app_id)

@router.get("/list/", status_code=status.HTTP_200_OK, response_model=List[AppListItem])
def get_apps(db: db_dependency, status: str | None = None, page: int = 1, size: int = 20):
    logger.info("Fetching list of apps for status: %s page: %d size: %d", status, page, size)
    if status and status in [s.value for s in AppStatus]:
        apps = db.query(AppModel).filter(AppModel.status == status).offset((page-1)*size).limit(size).all()
    else:
        apps = db.query(AppModel).offset((page-1)*size).limit(size).all()
    logger.debug("Found %d apps in database.", len(apps))
    return [
        {
            "id": app.id,
            'name': app.name,
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
def get_app(db: db_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Fetching details for app_id: %s", app_id)
    app = db.query(AppModel).filter(AppModel.id == app_id).first()
    if app is None:
        logger.warning("App with ID %s not found.", app_id)
        raise AppNotFoundError(detail="App not found")
    
    logger.debug("App %s found. Status: %s", app_id, app.status.value)
    return {
        'id': app.id,
        'name': app.name,
        'repo_url': app.repo_url,
        'subdomain': app.subdomain,
        'internal_port': app.internal_port,
        'container_port': app.container_port,
        'branch': app.branch,
        'build_path': app.build_path,
        'dockerfile_path': app.dockerfile_path,
        'status': app.status.value,
        'created_at': app.created_at,
        'updated_at': app.updated_at,
        'env': app.env
    }

@router.post("/{app_id}/deploy", status_code=status.HTTP_201_CREATED)
def deploy_app(props: AppDeployRequestModel, db: db_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Deployment triggered for app_id: %s", app_id)
    app = db.query(AppModel).filter(AppModel.id == app_id).first()

    if app is None:
        logger.error("Deployment failed: App %s not found.", app_id)
        raise AppNotFoundError(detail="App not found")

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
        logger.debug("ForceRebuild: True; Cleaning existing app directory: %s", app_dir)
        shutil.rmtree(app_dir)
    logger.info("Ensuring directory exists: %s", app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Starting git clone/pull for app %s", app_id)
        clone_or_pull_repo(str(app.repo_url), app_dir)
        logger.info("Code successfully fetched from github for app %d", app_id)
        app.status = AppStatus.PREPARED
        db.commit()

        logger.info("Starting docker build for app %s", app_id)
        docker_build(app, app_dir, build_args=props.build_args or {}, clear_cache=props.clear_cache or False)
        logger.info("Docker build successful for app %s", app_id)

        # Free the old container so its port is released before allocating a new one
        container_name = f"app_{app.id}_container"
        container_id = docker_container_exists(container_name)
        if container_id:
            logger.info("Releasing port from existing container %s", container_name)
            docker_remove_container(container_name, container_id)
            app.internal_port = None
            db.commit()

        # Dynamically allocate the first free port from the OS + DB
        app.internal_port = allocate_free_port(db)
        db.commit()
        logger.info("Allocated port %d for app %s", app.internal_port, app_id)

        logger.info("Initiating Docker Run Logic!")
        Config.BASE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        docker_run(app, app_dir, env_vars=props.env or {})
        logger.info(f"Application Successfully Started at port {app.internal_port}")
        app.status = AppStatus.RUNNING
        logger.info("App %s state updated to RUNNING.", app_id)
        db.commit()
    except Exception as e:
        logger.error("Deployment failed for app %s", str(e))
        app.status = AppStatus.ERROR
        db.commit()
        raise  # Re-raise — the global handler catches AppBaseError subtypes
    return {
        "id": app.id,
        "status": app.status.value
    }

