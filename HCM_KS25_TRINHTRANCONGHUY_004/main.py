from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import create_engine, Column, Integer, String, asc
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Optional, Any

load_dotenv()

class Settings:
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_NAME: str = os.getenv("DB_NAME", "class_section_db")

    @property
    def DATABASE_URL(self) -> str:
        if not self.DB_PASSWORD:
            return f"mysql+pymysql://{self.DB_USER}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ClassSection(Base):
    __tablename__ = "class_sections"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subject_name = Column(String(100), nullable=False)
    class_code = Column(String(50), nullable=False, unique=True)
    teacher_name = Column(String(100), nullable=False)
    student_count = Column(Integer, default=0)

class ClassSectionBase(BaseModel):
    subject_name: str = Field(..., min_length=2, max_length=100)
    class_code: str = Field(..., min_length=2, max_length=50)
    teacher_name: str = Field(..., min_length=2, max_length=100)
    student_count: int = Field(0, ge=0)

class ClassSectionCreate(ClassSectionBase):
    pass

class ClassSectionUpdate(BaseModel):
    subject_name: Optional[str] = None
    class_code: Optional[str] = None
    teacher_name: Optional[str] = None
    student_count: Optional[int] = None

class ClassSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subject_name: str
    class_code: str
    teacher_name: str
    student_count: int

class StandardResponse(BaseModel):
    statusCode: int
    data: Optional[Any] = None
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[Any] = None

def get_all_class_sections(db: Session):
    return db.query(ClassSection).order_by(asc(ClassSection.id)).all()

def search_class_sections(db: Session, subject_name: str):
    return db.query(ClassSection).filter(ClassSection.subject_name.ilike(f"%{subject_name}%")).all()

def get_class_section_by_id(db: Session, section_id: int):
    section = db.query(ClassSection).filter(ClassSection.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
    return section

def create_class_section(db: Session, data: dict):
    existing = db.query(ClassSection).filter(ClassSection.class_code == data["class_code"]).first()
    if existing:
        raise HTTPException(status_code=409, detail="Mã lớp đã tồn tại")
    new_section = ClassSection(**data)
    db.add(new_section)
    db.commit()
    db.refresh(new_section)
    return new_section

def update_class_section(db: Session, section_id: int, data: dict):
    section = get_class_section_by_id(db, section_id)
    for key, value in data.items():
        if value is not None:
            setattr(section, key, value)
    db.commit()
    db.refresh(section)
    return section

def delete_class_section(db: Session, section_id: int):
    section = get_class_section_by_id(db, section_id)
    db.delete(section)
    db.commit()
    return True

app = FastAPI(title="Quản Lý Lớp Học Phần")

Base.metadata.create_all(bind=engine)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "statusCode": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "data": None,
            "message": "Dữ liệu đầu vào không hợp lệ!",
            "timestamp": datetime.now().isoformat(),
            "error": exc.errors()
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "statusCode": exc.status_code,
            "data": None,
            "message": exc.detail,
            "timestamp": datetime.now().isoformat(),
            "error": str(exc.detail)
        }
    )

@app.get("/")
def root():
    return {"message": "API Quản lý Lớp Học Phần đang chạy."}

@app.get("/class-sections", response_model=StandardResponse)
def get_all(request: Request, db: Session = Depends(get_db)):
    sections = get_all_class_sections(db)
    return StandardResponse(
        statusCode=200,
        data=[ClassSectionResponse.model_validate(s).model_dump() for s in sections],
        message="Lấy danh sách lớp học phần thành công",
        error=None
    )

@app.get("/class-sections/search", response_model=StandardResponse)
def search(request: Request, subject_name: str, db: Session = Depends(get_db)):
    sections = search_class_sections(db, subject_name)
    return StandardResponse(
        statusCode=200,
        data=[ClassSectionResponse.model_validate(s).model_dump() for s in sections],
        message="Tìm kiếm lớp học phần thành công",
        error=None
    )

@app.get("/class-sections/{section_id}", response_model=StandardResponse)
def get_one(request: Request, section_id: int, db: Session = Depends(get_db)):
    section = get_class_section_by_id(db, section_id)
    return StandardResponse(
        statusCode=200,
        data=ClassSectionResponse.model_validate(section).model_dump(),
        message="Lấy chi tiết lớp học phần thành công",
        error=None
    )

@app.post("/class-sections", response_model=StandardResponse, status_code=201)
def create(request: Request, body: ClassSectionCreate, db: Session = Depends(get_db)):
    new_section = create_class_section(db, body.model_dump())
    return StandardResponse(
        statusCode=201,
        data=ClassSectionResponse.model_validate(new_section).model_dump(),
        message="Thêm mới lớp học phần thành công",
        error=None
    )

@app.put("/class-sections/{section_id}", response_model=StandardResponse)
def update(request: Request, section_id: int, body: ClassSectionUpdate, db: Session = Depends(get_db)):
    updated = update_class_section(db, section_id, body.model_dump())
    return StandardResponse(
        statusCode=200,
        data=ClassSectionResponse.model_validate(updated).model_dump(),
        message="Cập nhật lớp học phần thành công",
        error=None
    )

@app.delete("/class-sections/{section_id}", response_model=StandardResponse)
def delete(request: Request, section_id: int, db: Session = Depends(get_db)):
    delete_class_section(db, section_id)
    return StandardResponse(
        statusCode=200,
        data=None,
        message="Xóa lớp học phần thành công",
        error=None
    )