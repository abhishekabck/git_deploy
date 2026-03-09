from pydantic import BaseModel, Field

class AppResponseModel(BaseModel):
    id: int = Field(description="Application ID")
    subdomain: str = Field(description="Subdomain")
    container_port: int = Field(description="Port of Application.")
    status: str = Field(description="Status of Application")

