"""Pydantic schemas（请求 / 响应模型）。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# ---------- 用户 / 认证 ----------


class RegisterRequest(BaseModel):
    email: str
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)


class SendCodeRequest(BaseModel):
    email: str
    purpose: str = "login"  # login | register


class LoginRequest(BaseModel):
    email: str
    code: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MeOut(UserOut):
    pass


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ---------- 学校 / 年级 / 班级 ----------


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    province: str = ""
    city: str = ""


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None


class GradeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    classes: List[str] = []


class ClassOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class GradeOut(BaseModel):
    id: int
    name: str
    classes: List[ClassOut]

    class Config:
        from_attributes = True


class SchoolDetail(BaseModel):
    id: int
    name: str
    province: str
    city: str
    updated_at: datetime
    grades: List[GradeOut]
    has_excel: bool

    class Config:
        from_attributes = True


# ---------- 杂项配置 ----------


class ExtraConfigUpdate(BaseModel):
    """key -> JSON 字符串（可为任意 JSON 文本）。"""
    configs: dict


# ---------- 分享 ----------


class ShareCreate(BaseModel):
    class_id: Optional[int] = None  # null = 全校链接


class ShareOut(BaseModel):
    id: int
    token: str
    class_id: Optional[int]
    class_name: Optional[str]
    is_active: bool
    url: str
    created_at: datetime


# ---------- NTP 时间同步 ----------


class NtpServerUpdate(BaseModel):
    """创建 / 更新学校 NTP 服务（只传需要改的字段）。

    daily_offset_ms：每 24 小时累积的偏移量（毫秒），走快为正、走慢为负。
    """

    enabled: Optional[bool] = None
    daily_offset_ms: Optional[int] = None
    timezone: Optional[str] = None
    port: Optional[int] = None
    note: Optional[str] = None


class NtpCalibrateRequest(BaseModel):
    """手动校准：填入学校时钟此刻显示的时间。

    school_time 支持 "HH:MM:SS"（默认今天）或 "YYYY-MM-DD HH:MM:SS"。
    keep_daily_offset 为 True 时保留每日偏移量，只把当前累积误差吸收进基准偏移。
    """

    school_time: str
    keep_daily_offset: bool = True


# ---------- 管理概览 ----------


class AdminOverview(BaseModel):
    schools_count: int
    users_count: int
    shares_count: int
    schools: List[SchoolDetail]
