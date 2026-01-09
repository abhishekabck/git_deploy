from fastapi.exceptions import HTTPException
from fastapi import APIRouter, Depends
from fastapi import Path as ApiPath
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Annotated, List
from starlette import status
from database import SessionLocal
from models import AppModel, AppStatus
from datetime import datetime
from pathlib import Path
from services.deploy import validate_github_repo, clone_or_pull_repo
from services.docker import docker_build, docker_run
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/apps",
    tags=["apps"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

BASE_APPS_DIR = Path("/opt/apps")
BASE_APPS_DIR.mkdir(parents=True, exist_ok=True)

# dependencies
db_dependency = Annotated[Session, Depends(get_db)]


## request models

class AppRequestModel(BaseModel):
    repo_url: str = Field(description="Repository URL")
    container_port: int = Field(gt=1023, lt=65536, description="Project Port")

    model_config = {
        "json_schema_extra": {
            "example": {
                "repo_url": "https://github.com/{username}/{repo_name}.git",
                "container_port": 8000,
            }
        }
    }


###  >>>>>>>>>>>>>>>>>> Response Models <<<<<<<<<<<<<<<<<<<<<<<<< ###
class AppResponseModel(BaseModel):
    id: int = Field(description="Application ID")
    subdomain: str = Field(description="Subdomain")
    container_port: int = Field(description="Port of Application.")
    status: str = Field(description="Status of Application")


class AppListItem(BaseModel):
    id: int
    subdomain: str
    container_port: int
    status: str

class AppDetail(AppListItem):
    repo_url: str
    internal_port: int
    created_at: datetime
    updated_at: datetime


# >>>>>>>>>>>>> End response models <<<<<<<<<<<<<<<<<<<<


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppResponseModel)
def create_app(model: AppRequestModel, db: db_dependency):
    logger.info("Initiating App Create Request for repo: %s", model.repo_url)
    try:
        logger.debug("Validating GitHub repository URL: %s", model.repo_url)
        validate_github_repo(model.repo_url)
    except PermissionError as e:
        logger.error("Permission error validating repo %s: %s", model.repo_url, str(e))
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        logger.warning("Validation error for repo %s: %s", model.repo_url, str(e))
        raise HTTPException(status_code=400, detail=str(e))

    new_app = AppModel(repo_url=model.repo_url, status=AppStatus.CREATED, container_port=model.container_port)
    db.add(new_app)
    db.flush()  ## i used because it attaches id without commiting
    
    app_id = new_app.id
    new_app.subdomain = f"app-{app_id}"
    new_app.internal_port = 10000 + app_id
    
    logger.info("Created app record in DB with ID: %s, Internal Port: %s", app_id, new_app.internal_port)
    
    db.add(new_app)
    db.commit()
    logger.info("Successfully committed app %s to database.", app_id)
    
    return {
        "id": new_app.id,
        "subdomain": new_app.subdomain,
        "container_port": new_app.container_port,
        "status": new_app.status.value
    }


@router.get("", status_code=status.HTTP_200_OK, response_model=List[AppListItem])
def get_apps(db: db_dependency):
    logger.info("Fetching list of all apps.")
    apps = db.query(AppModel).all()
    logger.debug("Found %d apps in database.", len(apps))
    response = []

    for app in apps:
        response.append(
            {
                "id": app.id,
                "subdomain": app.subdomain,
                "container_port": app.container_port,
                "status": app.status.value,
            }
        )
    
    return response

@router.get("/{app_id}", status_code=status.HTTP_200_OK, response_model=AppDetail)
def get_app(db: db_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Fetching details for app_id: %s", app_id)
    app = db.query(AppModel).filter(AppModel.id == app_id).first()
    if app is None:
        logger.warning("App with ID %s not found.", app_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    
    logger.debug("App %s found. Status: %s", app_id, app.status.value)
    return {
        'id': app.id,
        'repo_url': app.repo_url,
        'subdomain': app.subdomain,
        'internal_port': app.internal_port,
        'container_port': app.container_port,
        'status': app.status.value,
        'created_at': app.created_at,
        'updated_at': app.updated_at
    }



@router.post("/{app_id}/deploy", status_code=status.HTTP_201_CREATED)
def deploy_app(db: db_dependency, app_id: int = ApiPath(gt=0)):
    logger.info("Deployment triggered for app_id: %s", app_id)
    app = db.query(AppModel).filter(AppModel.id == app_id).first()

    if app is None:
        logger.error("Deployment failed: App %s not found.", app_id)
        raise HTTPException(status_code=404, detail="App not found")

    app_dir = BASE_APPS_DIR / f"app-{app.id}"
    logger.info("Ensuring directory exists: %s", app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Starting git clone/pull for app %s", app_id)
        clone_or_pull_repo(str(app.repo_url), app_dir)
        logger.info("Git operation successful for app %s", app_id)
    except Exception as e:
        logger.exception("Git operation failed for app %s", app_id)
        app.status = AppStatus.ERROR
        db.commit()
        if isinstance(e, PermissionError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        if isinstance(e, (ValueError, RuntimeError)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise e

    # integrating docker build here
    try:
        logger.info("Starting docker build for app %s", app_id)
        docker_build(app, app_dir)
        logger.info("Docker build successful for app %s", app_id)
    except FileNotFoundError as e:
        logger.error("Dockerfile missing for app %s", app_id)
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dockerfile is not present in repository."
        )
    except RuntimeError as e:
        logger.error("Docker build failed for app %s: %s", app_id, str(e))
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"{e}"
        )

    # docker run
    try:
        logger.info("Initiating Docker Run Logic!")
        docker_run(app, app_dir)
        logger.info(f"Application Successfully Started at port {app.internal_port}")
        app.status = AppStatus.RUNNING
        logger.info("App %s state updated to RUNNING.", app_id)
        db.commit()
    except FileNotFoundError as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except RuntimeError as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {
        "id": app.id,
        "status": app.status.value
    }
