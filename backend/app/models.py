"""SQLAlchemy 数据模型。

角色模型：
- superadmin 超级管理员：查看平台运行状态 + 拥有普通管理员全部权限
- admin 普通管理员：创建学校、上传课程表、创建分享链接 + 拥有游客全部权限
- 游客：通过 token 访问分享链接
"""
import secrets
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _token() -> str:
    return secrets.token_urlsafe(24)


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=False)
    # 校验摘要：sha512(sha512_hex(password) + SECRET_KEY)，注册与登录各校验一次
    password_hash = Column(String(200), nullable=True)
    role = Column(String(20), nullable=False, default="admin")  # admin | superadmin
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    schools = relationship("School", back_populates="owner")


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    code = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    province = Column(String(100), nullable=False, default="")
    city = Column(String(100), nullable=False, default="")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="schools")
    grades = relationship(
        "Grade", back_populates="school", cascade="all, delete-orphan",
        order_by="Grade.sort_order",
    )
    shares = relationship("ShareLink", back_populates="school", cascade="all, delete-orphan")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    school = relationship("School", back_populates="grades")
    classes = relationship(
        "SchoolClass", back_populates="grade", cascade="all, delete-orphan",
        order_by="SchoolClass.sort_order",
    )


class SchoolClass(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    grade_id = Column(Integer, ForeignKey("grades.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    grade = relationship("Grade", back_populates="classes")
    schedules = relationship("DaySchedule", back_populates="cls", cascade="all, delete-orphan")
    links = relationship("ShareLink", back_populates="cls", cascade="all, delete-orphan")


class DaySchedule(Base):
    """某天班级课程表：cells = [{"period": 1, "subject_code": 3}, ...]。"""

    __tablename__ = "day_schedules"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    day = Column(Integer, nullable=False)  # 1=周一 … 7=周日（对应 sheet 命名）
    cells_json = Column(Text, nullable=False, default="[]")

    cls = relationship("SchoolClass", back_populates="schedules")

    __table_args__ = (UniqueConstraint("class_id", "day", name="uq_day_schedule"),)


class SchoolConfig(Base):
    """config sheet 解析结果：科目与时间线（JSON 文本）。"""

    __tablename__ = "school_configs"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), unique=True, nullable=False)
    subjects_json = Column(Text, nullable=False, default="[]")
    timelines_json = Column(Text, nullable=False, default="{}")
    uploaded_at = Column(DateTime, nullable=False, default=utcnow)


class ExtraConfig(Base):
    """杂项配置（config sheet AB/AC 列导入，管理员可继续编辑）。"""

    __tablename__ = "extra_configs"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    key = Column(String(200), nullable=False)
    value_json = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (UniqueConstraint("school_id", "key", name="uq_extra_config"),)


class SchoolMember(Base):
    """学校协作成员（多用户协作编辑）。"""

    __tablename__ = "school_members"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, default="editor")  # owner | editor
    created_at = Column(DateTime, nullable=False, default=utcnow)

    user = relationship("User")

    __table_args__ = (UniqueConstraint("school_id", "user_id", name="uq_school_member"),)


class ShareLink(Base):
    __tablename__ = "share_links"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)  # null = 全校
    token = Column(String(64), unique=True, index=True, nullable=False, default=_token)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    school = relationship("School", back_populates="shares")
    cls = relationship("SchoolClass", back_populates="links")
    creator = relationship("User")
