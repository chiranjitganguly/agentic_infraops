from pydantic import BaseModel


class VMParameters(BaseModel):
    machine_type: str
    disk_size_gb: int = 50
    image_family: str = "debian-12"
    image_project: str = "debian-cloud"
    network: str = "default"
    tags: list[str] = []
