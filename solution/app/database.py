import json
from os import environ
from typing import Annotated, Any

from fastapi import Depends
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, col, create_engine, select

from app.models import FraudRule, FraudRuleDB


class BaseModelEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, BaseModel):
            return o.model_dump(mode="json")

        return super().default(o)


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
    engine = create_engine(
        psql_url,
        json_serializer=lambda obj: json.dumps(
            obj,
            ensure_ascii=False,
            cls=BaseModelEncoder,
        ),
    )


def setup_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def fetch_db_fraud_rules(session: Session):
    return session.exec(
        select(FraudRuleDB)
        .where(FraudRuleDB.enabled)
        .order_by(col(FraudRuleDB.priority).asc())
    )


def fetch_fraud_rules(session: Session):
    return map(FraudRule.from_db_rule, fetch_db_fraud_rules(session))


SessionDep = Annotated[Session, Depends(get_session)]
