"""管理路由：学校/年级/班级/Excel 上传/分享链接/杂项配置/协作成员。"""
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import config as app_config
from .. import schemas
from ..db import get_db
from ..deps import can_edit_school, require_admin
from ..excel_parser import ExcelFormatError, parse_workbook
from ..models import (
    DaySchedule,
    ExtraConfig,
    Grade,
    NtpServer,
    School,
    SchoolClass,
    SchoolConfig,
    SchoolMember,
    ShareLink,
    User,
)
from ..ntp import ntp_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_school_or_404(db: Session, school_id: int) -> School:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "学校不存在")
    return school


def _school_detail(db: Session, school: School) -> dict:
    has_excel = (
        db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first() is not None
    )
    return {
        "id": school.id,
        "name": school.name,
        "province": school.province,
        "city": school.city,
        "updated_at": school.updated_at,
        "has_excel": has_excel,
        "grades": [
            {
                "id": g.id,
                "name": g.name,
                "classes": [{"id": c.id, "name": c.name} for c in g.classes],
            }
            for g in school.grades
        ],
    }


@router.post("/schools", status_code=status.HTTP_201_CREATED)
def create_school(body: schemas.SchoolCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    school = School(name=body.name.strip(), province=body.province.strip(),
                    city=body.city.strip(), owner_id=user.id)
    db.add(school)
    db.commit()
    db.refresh(school)
    db.add(SchoolMember(school_id=school.id, user_id=user.id, role="owner"))
    db.commit()
    return _school_detail(db, school)


@router.get("/schools")
def list_my_schools(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if user.role == "superadmin":
        schools = db.query(School).order_by(School.id).all()
    else:
        member_ids = [
            m.school_id for m in db.query(SchoolMember).filter(
                SchoolMember.user_id == user.id).all()
        ]
        schools = db.query(School).filter(School.id.in_(member_ids)).order_by(School.id).all()
    return [_school_detail(db, s) for s in schools]


@router.get("/schools/{school_id}")
def get_school(school_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    return _school_detail(db, school)


@router.put("/schools/{school_id}")
def update_school(school_id: int, body: schemas.SchoolUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    if body.name is not None:
        school.name = body.name.strip()
    if body.province is not None:
        school.province = body.province.strip()
    if body.city is not None:
        school.city = body.city.strip()
    db.commit()
    return _school_detail(db, school)


@router.delete("/schools/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school(school_id: int, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    if user.role != "superadmin" and school.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有创建者或超管可以删除学校")
    db.delete(school)
    db.query(SchoolMember).filter(SchoolMember.school_id == school_id).delete()
    db.query(SchoolConfig).filter(SchoolConfig.school_id == school_id).delete()
    db.query(ExtraConfig).filter(ExtraConfig.school_id == school_id).delete()
    db.query(NtpServer).filter(NtpServer.school_id == school_id).delete()
    db.commit()
    if app_config.NTP_ENABLED:
        await ntp_service.refresh()  # 释放该校占用的 UDP 端口


@router.post("/schools/{school_id}/grades", status_code=status.HTTP_201_CREATED)
def create_grade(school_id: int, body: schemas.GradeCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    grade = Grade(school_id=school_id, name=body.name.strip(),
                  sort_order=len(school.grades))
    db.add(grade)
    db.flush()
    for i, cname in enumerate(body.classes):
        db.add(SchoolClass(grade_id=grade.id, name=cname.strip(), sort_order=i))
    db.commit()
    db.refresh(grade)
    return {"id": grade.id, "name": grade.name,
            "classes": [{"id": c.id, "name": c.name} for c in grade.classes]}


@router.post("/schools/{school_id}/upload")
async def upload_excel(school_id: int, file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    """上传格式化 Excel：清空旧课程表数据，重建年级/班级/课表，并导入杂项配置。"""
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")
    try:
        parsed = parse_workbook(io.BytesIO(data))
    except ExcelFormatError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Excel 格式错误：%s" % e)
    except Exception as e:  # openpyxl 的其它异常
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法解析文件：%s" % e)

    # 清理旧数据
    for g in list(school.grades):
        db.delete(g)
    db.query(SchoolConfig).filter(SchoolConfig.school_id == school_id).delete()
    db.query(DaySchedule).filter(
        DaySchedule.class_id.in_(
            db.query(SchoolClass.id).join(Grade).filter(Grade.school_id == school_id)
        )
    ).delete(synchronize_session=False)
    db.query(ShareLink).filter(ShareLink.school_id == school_id).delete()

    # 写入 config 解析结果
    db.add(SchoolConfig(
        school_id=school_id,
        subjects_json=json.dumps(parsed["subjects"], ensure_ascii=False),
        timelines_json=json.dumps(parsed["timelines"], ensure_ascii=False),
    ))

    # 重建年级/班级/课表
    for gi, grade_data in enumerate(parsed["grades"]):
        grade = Grade(school_id=school_id, name=grade_data["name"], sort_order=gi)
        db.add(grade)
        db.flush()
        for ci, (cname, cells) in enumerate(grade_data["classes"].items()):
            cls = SchoolClass(grade_id=grade.id, name=cname, sort_order=ci)
            db.add(cls)
            db.flush()
            by_day = {}
            for cell in cells:
                by_day.setdefault(cell["day"], []).append(
                    {"period": cell["period"], "subject_code": cell["subject_code"]})
            for day, day_cells in by_day.items():
                db.add(DaySchedule(class_id=cls.id, day=day,
                                   cells_json=json.dumps(day_cells)))

    # 杂项配置（保留已手工编辑过的同名项：覆盖导入）
    existing = {e.key: e for e in
                db.query(ExtraConfig).filter(ExtraConfig.school_id == school_id).all()}
    for key, value in parsed["extras"].items():
        try:
            value_json = json.dumps(json.loads(value), ensure_ascii=False)
        except (ValueError, TypeError):
            value_json = json.dumps(value, ensure_ascii=False)
        if key in existing:
            existing[key].value_json = value_json
            existing[key].updated_by = user.id
            existing[key].updated_at = datetime.utcnow()
        else:
            db.add(ExtraConfig(school_id=school_id, key=key, value_json=value_json,
                               updated_by=user.id))

    school.updated_at = datetime.utcnow()
    db.commit()

    return {
        "grades": len(parsed["grades"]),
        "subjects": len(parsed["subjects"]),
        "timelines": len(parsed["timelines"]),
        "extras": len(parsed["extras"]),
    }


# ---------------- 分享链接 ----------------

@router.post("/schools/{school_id}/shares", status_code=status.HTTP_201_CREATED)
def create_share(school_id: int, body: schemas.ShareCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    """获取班级分享链接。每个班级的链接是固定的：重复调用返回同一个链接。"""
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    cls = None
    if body.class_id is not None:
        cls = db.get(SchoolClass, body.class_id)
        if cls is None or cls.grade.school_id != school_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    target_class_id = cls.id if cls else None
    link = db.query(ShareLink).filter(
        ShareLink.school_id == school_id,
        ShareLink.class_id == target_class_id,
    ).first()
    created = link is None
    if link is None:
        link = ShareLink(school_id=school_id, class_id=target_class_id,
                         created_by=user.id)
        db.add(link)
        db.commit()
        db.refresh(link)
    elif not link.is_active:
        link.is_active = True
        db.commit()
    out = _share_out(link, cls.name if cls else None)
    out["created"] = created
    return out


@router.get("/schools/{school_id}/shares")
def list_shares(school_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    links = db.query(ShareLink).filter(ShareLink.school_id == school_id).all()
    out = []
    for link in links:
        cname = link.cls.name if link.cls else None
        out.append(_share_out(link, cname))
    return out


@router.delete("/shares/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(link_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    link = db.get(ShareLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接不存在")
    can_edit_school(db, user, _get_school_or_404(db, link.school_id))
    db.delete(link)
    db.commit()


def _share_out(link: ShareLink, class_name) -> dict:
    return {
        "id": link.id,
        "token": link.token,
        "class_id": link.class_id,
        "class_name": class_name,
        "is_active": link.is_active,
        "url": "/share/" + link.token,
        "created_at": link.created_at,
    }


# ---------------- 杂项配置 ----------------

def _extra_out(row) -> dict:
    try:
        value = json.loads(row.value_json)
    except ValueError:
        value = row.value_json
    return {"key": row.key, "value": value, "updated_at": row.updated_at}


@router.get("/schools/{school_id}/extra-configs")
def list_extra_configs(school_id: int, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    rows = db.query(ExtraConfig).filter(ExtraConfig.school_id == school_id).all()
    return [_extra_out(r) for r in rows]


def _set_extra_config(db: Session, school_id: int, key: str, value, user_id: int):
    key = key.strip()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "配置名不能为空")
    if len(key) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "配置名过长（最多 200 字符）")
    existing = db.query(ExtraConfig).filter(
        ExtraConfig.school_id == school_id, ExtraConfig.key == key).first()
    value_json = json.dumps(value, ensure_ascii=False)
    if existing:
        existing.value_json = value_json
        existing.updated_by = user_id
        existing.updated_at = datetime.utcnow()
        row = existing
    else:
        row = ExtraConfig(school_id=school_id, key=key, value_json=value_json,
                          updated_by=user_id)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/schools/{school_id}/extra-configs")
def update_extra_configs(school_id: int, body: schemas.ExtraConfigUpdate,
                         db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    for key, value in body.configs.items():
        _set_extra_config(db, school_id, key, value, user.id)
    return {"updated": list(body.configs.keys())}


@router.post("/schools/{school_id}/extra-configs/{key:path}",
             status_code=status.HTTP_201_CREATED)
def add_extra_config(school_id: int, key: str, body: dict,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    """新增/覆盖一条杂项配置，body: {"value": ...}。"""
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    if "value" not in body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请求体需要 value 字段")
    row = _set_extra_config(db, school_id, key, body["value"], user.id)
    return _extra_out(row)


@router.delete("/schools/{school_id}/extra-configs/{key:path}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_extra_config(school_id: int, key: str, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(ExtraConfig).filter(
        ExtraConfig.school_id == school_id, ExtraConfig.key == key).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "配置项不存在：%s" % key)
    db.delete(row)
    db.commit()


@router.post("/schools/{school_id}/extra-configs-upload/{key:path}",
             status_code=status.HTTP_201_CREATED)
async def upload_extra_config(school_id: int, key: str, file: UploadFile = File(...),
                              db: Session = Depends(get_db),
                              user: User = Depends(require_admin)):
    """上传文件作为杂项配置内容（自动按扩展名识别 JSON/文本）。"""
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件过大（上限 5 MB）")
    text = data.decode("utf-8-sig", errors="strict") if not key.lower().endswith(
        (".png", ".jpg", ".jpeg", ".ico")) else None
    if text is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持文本/JSON 类配置文件")
    fname = (file.filename or key).lower()
    if fname.endswith(".json"):
        try:
            value = json.loads(text)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON 解析失败：%s" % e)
    else:
        value = text
    row = _set_extra_config(db, school_id, key, value, user.id)
    return _extra_out(row)


# ---------------- 协作成员 ----------------

@router.get("/schools/{school_id}/members")
def list_members(school_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    members = db.query(SchoolMember).filter(SchoolMember.school_id == school_id).all()
    return [{"id": m.id, "user_id": m.user_id, "username": m.user.username,
             "email": m.user.email, "role": m.role} for m in members]


@router.post("/schools/{school_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(school_id: int, email: str, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    school = _get_school_or_404(db, school_id)
    can_edit_school(db, user, school)
    target = db.query(User).filter(User.email == email.strip().lower()).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该邮箱对应用户不存在")
    exists = db.query(SchoolMember).filter(
        SchoolMember.school_id == school_id, SchoolMember.user_id == target.id).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "该用户已是协作成员")
    db.add(SchoolMember(school_id=school_id, user_id=target.id, role="editor"))
    db.commit()
    return {"user_id": target.id, "username": target.username, "email": target.email,
            "role": "editor"}


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    member = db.get(SchoolMember, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员不存在")
    can_edit_school(db, user, _get_school_or_404(db, member.school_id))
    if member.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能移除创建者")
    db.delete(member)
    db.commit()
