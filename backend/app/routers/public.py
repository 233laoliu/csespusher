"""公开路由（未登录可用）：主页学校分组、分享页数据、配置下载。"""
import json
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from .. import config as app_config
from ..converters import GENERATORS, build_day_events
from ..db import get_db
from ..models import DaySchedule, ExtraConfig, Grade, School, SchoolClass, SchoolConfig, ShareLink

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/site-info")
def site_info():
    """网站信息：下载按钮链接、页脚联系方式。"""
    return {
        "github_url": app_config.GITHUB_URL,
        "contact_email": app_config.CONTACT_EMAIL,
        "downloads": {
            "classisland": app_config.CLASSISLAND_RELEASE_URL,
            "classwidgets": app_config.CLASSWIDGETS_RELEASE_URL,
        },
    }


@router.get("/schools")
def list_schools(q: Optional[str] = Query(None, description="搜索关键词"),
                 province: Optional[str] = None, city: Optional[str] = None,
                 db: Session = Depends(get_db)):
    """按 省/市/校 分组返回已收集的学校列表。"""
    query = db.query(School)
    if province:
        query = query.filter(School.province == province)
    if city:
        query = query.filter(School.city == city)
    if q:
        like = "%%%s%%" % q.strip()
        query = query.filter(School.name.like(like))

    grouped = OrderedDict()
    for school in query.order_by(School.province, School.city, School.name).all():
        prov = school.province or "未分类"
        c = school.city or "未分类"
        grouped.setdefault(prov, {}).setdefault(c, []).append({
            "id": school.id, "name": school.name,
            "grade_count": len(school.grades),
        })
    return [
        {"province": prov, "cities": [
            {"city": c, "schools": schools} for c, schools in cities.items()
        ]}
        for prov, cities in grouped.items()
    ]


@router.get("/schools/{school_id}")
def school_public(school_id: int, db: Session = Depends(get_db)):
    """公开的学校详情：年级/班级列表（供班级查找）。"""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "学校不存在")
    return {
        "id": school.id,
        "name": school.name,
        "province": school.province,
        "city": school.city,
        "grades": [
            {"id": g.id, "name": g.name,
             "classes": [{"id": c.id, "name": c.name} for c in g.classes]}
            for g in school.grades
        ],
    }



def _disposition(filename: str) -> str:
    """同时提供 ASCII 回退文件名（含扩展名）与 RFC 5987 编码名，兼容所有浏览器。"""
    from urllib.parse import quote
    ascii_name = filename.encode("ascii", "ignore").decode("ascii")
    # 中文剥离后若剩余部分过短/只剩符号，用通用回退名
    stripped = ascii_name.replace("-", "").replace(".", "")
    if not stripped:
        ascii_name = "timetable." + filename.rsplit(".", 1)[-1]
    encoded = quote(filename, encoding="utf-8")
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, encoded)


def _fmt_hhmm(td) -> str:
    """timedelta 格式化为 HH:MM（补零）。"""
    total = int(td.total_seconds())
    return "%02d:%02d" % (total // 3600, (total % 3600) // 60)


def _week_events(events):
    """预览用：只保留上课事件，时间格式化为 HH:MM。"""
    return [
        {"type": ev["type"], "start": _fmt_hhmm(ev["start"]), "end": _fmt_hhmm(ev["end"]),
         "subject": ev["subject"] or "（自习/默认）"}
        for ev in events if ev["type"] != "break"
    ]


def _cors() -> dict:
    """允许客户端软件跨域读取配置原文。"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def _load_class_cells(db: Session, school: School, cls_id: int):
    """取某班级的课位数据，返回 (cfg, cls, cells)。"""
    cfg = db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first()
    if cfg is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该学校尚未上传课程表")
    cls = db.get(SchoolClass, cls_id)
    if cls is None or cls.grade.school_id != school.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    subjects = json.loads(cfg.subjects_json)
    timelines = json.loads(cfg.timelines_json)
    days = db.query(DaySchedule).filter(DaySchedule.class_id == cls.id).all()
    cells = []
    for d in days:
        for cell in json.loads(d.cells_json):
            cells.append({"day": d.day, "period": cell["period"],
                          "subject_code": cell["subject_code"]})
    return cfg, cls, cells, {"subjects": subjects, "timelines": timelines}


# ---------------- 公开班级页 ----------------

@router.get("/classes/{class_id}")
def class_public(class_id: int, db: Session = Depends(get_db)):
    """公开班级页数据：学校/班级信息 + 可用下载格式。"""
    cls = db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    school = cls.grade.school
    cfg = db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first()
    return {
        "class": {"id": cls.id, "name": cls.name},
        "grade": {"id": cls.grade.id, "name": cls.grade.name},
        "school": {"id": school.id, "name": school.name,
                   "province": school.province, "city": school.city},
        "has_excel": cfg is not None,
        "formats": ["cses", "classisland", "classwidgets"] if cfg else [],
    }


@router.get("/classes/{class_id}/download/{fmt}")
def class_download(class_id: int, fmt: str, db: Session = Depends(get_db)):
    """公开直接下载某班级的配置文件（无需分享链接）。"""
    if fmt not in GENERATORS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "不支持的格式：%s" % fmt)
    cls = db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    school = cls.grade.school
    cfg, cls, cells, parsed = _load_class_cells(db, school, class_id)
    generator, ext, mime = GENERATORS[fmt]
    try:
        content = generator(parsed, school.name, cls.grade.name, cls.name, cells, school.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "生成失败：%s" % e)
    extras = db.query(ExtraConfig).filter(ExtraConfig.school_id == school.id).all()
    headers = {"X-Extra-Config-Keys": ",".join(e.key for e in extras)} if extras else {}
    filename = "%s-%s-%s.%s" % (school.name, cls.grade.name, cls.name, ext)
    return Response(
        content=content.encode("utf-8"),
        media_type=mime,
        headers={"Content-Disposition": _disposition(filename), **headers},
    )


@router.get("/classes/{class_id}/raw/{fmt}")
def class_raw(class_id: int, fmt: str, db: Session = Depends(get_db)):
    """配置原文直链：供软件「从互联网导入配置」直接拉取（复制此 URL 即可）。"""
    if fmt not in GENERATORS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "不支持的格式：%s" % fmt)
    cls = db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    school = cls.grade.school
    cfg, cls, cells, parsed = _load_class_cells(db, school, class_id)
    generator, ext, mime = GENERATORS[fmt]
    try:
        content = generator(parsed, school.name, cls.grade.name, cls.name, cells, school.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "生成失败：%s" % e)
    extras = db.query(ExtraConfig).filter(ExtraConfig.school_id == school.id).all()
    headers = _cors()
    if extras:
        headers["X-Extra-Config-Keys"] = ",".join(e.key for e in extras)
    return Response(content=content.encode("utf-8"), media_type=mime + "; charset=utf-8",
                    headers=headers)


@router.options("/classes/{class_id}/raw/{fmt}")
def class_raw_options(class_id: int, fmt: str):
    return Response(status_code=204, headers=_cors())


@router.get("/classes/{class_id}/preview")
def class_preview(class_id: int, db: Session = Depends(get_db)):
    """公开班级课表预览。"""
    cls = db.get(SchoolClass, class_id)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    school = cls.grade.school
    cfg, cls, cells, parsed = _load_class_cells(db, school, class_id)
    from ..converters import DAY_NAMES
    week = []
    for day in sorted({c["day"] for c in cells}):
        events, err = build_day_events(parsed, cells, day)
        if err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, err)
        week.append({
            "day": day,
            "name": DAY_NAMES[day - 1],
            "events": _week_events(events),
        })
    return {"class": cls.name, "grade": cls.grade.name, "school": school.name, "week": week}


# ---------------- 分享链接 ----------------

def _resolve_link(token: str, db: Session):
    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if link is None or not link.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接不存在或已失效")
    school = link.school
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "学校已删除")
    return link, school


@router.get("/share/{token}")
def share_page(token: str, db: Session = Depends(get_db)):
    """分享页数据：学校/班级信息 + 可用的下载格式。"""
    link, school = _resolve_link(token, db)
    cfg = db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first()

    if link.class_id:
        cls = link.cls
        grade = cls.grade
        classes = [{"id": cls.id, "name": cls.name, "grade": grade.name}]
    else:
        classes = [
            {"id": c.id, "name": c.name, "grade": g.name}
            for g in school.grades for c in g.classes
        ]
    return {
        "school": {"id": school.id, "name": school.name,
                   "province": school.province, "city": school.city},
        "classes": classes,
        "has_excel": cfg is not None,
        "formats": ["cses", "classisland", "classwidgets"] if cfg else [],
        "downloads": {
            "classisland": app_config.CLASSISLAND_RELEASE_URL,
            "classwidgets": app_config.CLASSWIDGETS_RELEASE_URL,
        },
    }


@router.get("/share/{token}/download/{fmt}")
def share_download(token: str, fmt: str, class_id: Optional[int] = None,
                   db: Session = Depends(get_db)):
    """下载指定格式的课程表配置文件。"""
    if fmt not in GENERATORS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "不支持的格式：%s" % fmt)
    link, school = _resolve_link(token, db)
    cfg = db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first()
    if cfg is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该学校尚未上传课程表")

    # 选择班级：链接带班级则固定；全校链接需指定 class_id
    if link.class_id:
        cls = link.cls
    else:
        if class_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "全校链接需要指定班级 (class_id)")
        cls = db.get(SchoolClass, class_id)
        if cls is None or cls.grade.school_id != school.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")
    grade = cls.grade

    subjects = json.loads(cfg.subjects_json)
    timelines = json.loads(cfg.timelines_json)
    days = db.query(DaySchedule).filter(DaySchedule.class_id == cls.id).all()
    cells = []
    for d in days:
        for cell in json.loads(d.cells_json):
            cells.append({"day": d.day, "period": cell["period"],
                          "subject_code": cell["subject_code"]})

    parsed = {"subjects": subjects, "timelines": timelines}
    generator, ext, mime = GENERATORS[fmt]
    try:
        content = generator(parsed, school.name, grade.name, cls.name, cells, school.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "生成失败：%s" % e)

    # 附加杂项配置（classisland/classwidgets 独有配置）
    extras = db.query(ExtraConfig).filter(ExtraConfig.school_id == school.id).all()
    headers = {"X-Extra-Config-Keys": ",".join(e.key for e in extras)} if extras else {}

    filename = "%s-%s-%s.%s" % (school.name, grade.name, cls.name, ext)
    return Response(
        content=content.encode("utf-8"),
        media_type=mime,
        headers={"Content-Disposition": _disposition(filename), **headers},
    )


@router.get("/share/{token}/preview")
def share_preview(token: str, class_id: Optional[int] = None, db: Session = Depends(get_db)):
    """课程表预览（分享页内展示）。"""
    link, school = _resolve_link(token, db)
    cfg = db.query(SchoolConfig).filter(SchoolConfig.school_id == school.id).first()
    if cfg is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该学校尚未上传课程表")

    if link.class_id:
        cls = link.cls
    else:
        if class_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "全校链接需要指定班级 (class_id)")
        cls = db.get(SchoolClass, class_id)
        if cls is None or cls.grade.school_id != school.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "班级不存在")

    subjects = json.loads(cfg.subjects_json)
    timelines = json.loads(cfg.timelines_json)
    days = db.query(DaySchedule).filter(DaySchedule.class_id == cls.id).all()
    cells = []
    for d in days:
        for cell in json.loads(d.cells_json):
            cells.append({"day": d.day, "period": cell["period"],
                          "subject_code": cell["subject_code"]})
    parsed = {"subjects": subjects, "timelines": timelines}

    from ..converters import DAY_NAMES
    week = []
    for day in sorted({c["day"] for c in cells}):
        events, err = build_day_events(parsed, cells, day)
        if err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, err)
        week.append({
            "day": day,
            "name": DAY_NAMES[day - 1],
            "events": _week_events(events),
        })
    return {"class": cls.name, "grade": cls.grade.name, "school": school.name, "week": week}
