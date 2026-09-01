from app.db.db import Base
from uuid import uuid4, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String


class User(Base):
    __tablename__ = "users"

    client_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(30), unique=True)
