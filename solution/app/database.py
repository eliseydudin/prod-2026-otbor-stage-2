from os import environ
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

if environ.get("DEBUG") is not None:
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
else:
    user = environ["DB_USER"]
    password = environ["DB_PASSWORD"]
    host = environ["DB_HOST"]
    db_name = environ["DB_NAME"]

    psql_url = f"postgresql+psycopg2://{user}:{password}@{host}/{db_name}"
    engine = create_engine(psql_url)


def setup_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
