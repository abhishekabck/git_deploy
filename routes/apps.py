from fastapi.exceptions import HTTPException
from fastapi import APIRouter, Depends, Path, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Annotated, List
from starlette import status
from database import SessionLocal
from models import AppModel, AppStatus
from datetime import datetime
from pathlib import Path
import subprocess
import requests
from urllib.parse import urlparse

BASE_APPS_DIR = "/opt/apps"

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

db_dependency = Annotated[Session, Depends(get_db)]


class AppRequestModel(BaseModel):
    repo_url: str = Field(description="Repository URL", example="https://github.com/username/repo.git")


###  >>>>>>>>>>>>>>>>>> Response Models <<<<<<<<<<<<<<<<<<<<<<<<< ###
class AppResponseModel(BaseModel):
    id: int = Field(description="Application ID")
    subdomain: str = Field(description="Subdomain")
    internal_port: int = Field(description="Internal port of Application")
    status: str = Field(description="Status of Application")


class AppListItem(BaseModel):
    id: int
    subdomain: str
    status: str

class AppDetail(AppListItem):
    repo_url: str
    internal_port: int
    created_at: datetime
    updated_at: datetime


def validate_github_repo(url: str) -> bool:
    return url.startswith("https://github.com/") and len(url.split("/")) >= 5

@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppResponseModel)
def create_app(repo: AppRequestModel, db: db_dependency):
    
    if not validate_github_repo(repo.repo_url):
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GitHub repository URL format")

    new_app = AppModel(repo_url=repo.repo_url, status=AppStatus.CREATED)
    db.add(new_app)
    db.flush()  ## i used because it attaches id without commiting
    id = new_app.id
    new_app.subdomain = f"app-{id}"
    new_app.internal_port = 10000+id
    db.add(new_app)
    db.commit()
    
    
    return {
        "id": id,
        "subdomain": new_app.subdomain,
        "internal_port": new_app.internal_port,
        "status": new_app.status.value
    }


@router.get("", status_code=status.HTTP_200_OK, response_model=List[AppListItem])
def get_apps(db: db_dependency):
    apps = db.query(AppModel).all()
    response = list()

    for app in apps:
        response.append(
            {
                "id": app.id,
                "subdomain": app.subdomain,
                "status": app.status.value
            }
        )
    
    return response

@router.get("/{app_id}", status_code=status.HTTP_200_OK, response_model=AppDetail)
def get_app(db: db_dependency, app_id: int = Path(gt=0)):
    app = db.query(AppModel).filter(AppModel.id == app_id).first()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    return {
        'id': app.id,
        'repo_url': app.repo_url,
        'subdomain': app.subdomain,
        'internal_port': app.internal_port,
        'status': app.status.value,
        'created_at': app.created_at,
        'updated_at': app.updated_at
    }


# deploy github_logic

def validate_github_repo(repo_url: str) -> None:
    if not repo_url.startswith("https://github.com/"):
        raise ValueError("Only GitHub repositories are supported")

    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")

    if len(parts) < 2:
        raise ValueError("Invalid GitHub repository URL")

    owner, repo = parts[0], parts[1].replace(".git", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url, timeout=5)

    if response.status_code == 404:
        raise ValueError("Repository does not exist")

    if response.status_code != 200:
        raise RuntimeError("Failed to fetch repository metadata")

    if response.json().get("private"):
        raise PermissionError("Private repositories are not supported")



def clone_or_pull_repo(repo_url: str, app_dir: Path) -> None:
    git_dir = app_dir / ".git"

    validate_github_repo(repo_url)

    if not git_dir.exists():
        result = subprocess.run(
            ["git", "clone", repo_url, "."],
            cwd=app_dir,
            capture_output=True,
            text=True
        )
    else:
        result = subprocess.run(
            ["git", "pull"],
            cwd=app_dir,
            capture_output=True,
            text=True
        )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    

@router.post("/{app_id}/deploy", status_code=status.HTTP_201_CREATED)
def deploy_app(db: db_dependency, app_id: int = Path(gt=0)):
    app = db.query(AppModel).filter(AppModel.id == app_id).first()

    if app is None:
        raise HTTPException(status_code=404, detail="App not found")

    if app.status == AppStatus.RUNNING:
        raise HTTPException(status_code=400, detail="App is already running")

    app_dir = BASE_APPS_DIR / f"app-{app.id}"
    app_dir.mkdir(parents=True, exist_ok=True)

    try:
        clone_or_pull_repo(app.repo_url, app_dir)
    except PermissionError as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        app.status = AppStatus.ERROR
        db.commit()
        raise HTTPException(status_code=400, detail=f"Git error: {e}")

    app.status = AppStatus.PREPARED
    db.commit()

    return {
        "id": app.id,
        "status": app.status.value
    }


class AppStatusUpdate(BaseModel):
    status: str = Field(description="Status of Application")


@router.put("/{app_id}/update_status", status_code=status.HTTP_201_CREATED)
def update_app_status(db: db_dependency, app_id: int = Path(gt=0), status: AppStatusUpdate = Body(...)):
    app = db.query(AppModel).filter(AppModel.id == app_id).first()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    if status.status not in [member.value for member in AppStatus]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    app.status = AppStatus(status.status)
    db.commit()
    return {
        "id": app.id,
        "status": app.status.value
    }
    