import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str  # длину/сложность валидируем в сервисе, не в схеме


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # позволяет строить схему из ORM-объекта

    id: uuid.UUID
    email: EmailStr
    is_active: bool