from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")

engine = create_engine(
    DATABASE_URL,
    # Equilibrio perfecto: Un tope de 300 conexiones por worker para no acaparar tanta memoria,
    # pero manteniendo una sala de espera gigantesca para que nadie se quede fuera.
    pool_size=50,          
    max_overflow=250,      
    pool_timeout=60,       
    pool_recycle=1800      
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()