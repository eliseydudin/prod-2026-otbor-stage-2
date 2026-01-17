from os import environ
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

if environ["DEBUG"]:
    # lazy local testing :)
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
else:
    # TODO
    print("currently unsupported!")
    exit(1)


def setup_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
