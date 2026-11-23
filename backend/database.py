import os
from sqlmodel import create_engine, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///database.db")

# Render usa postgres://. Fixa o driver psycopg2 explicitamente: a partir do
# SQLAlchemy 2.1, "postgresql://" passa a usar psycopg (v3) por padrão,
# que não está instalado (requirements usa psycopg2-binary).
for prefixo in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefixo):
        DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len(prefixo):]
        break

engine = create_engine(DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session