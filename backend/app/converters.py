"""格式转换器：将解析后的数据生成三种软件的配置文件内容。

- CSES v2（YAML）：https://github.com/SmartTeachCN/CSES
- ClassIsland profile（JSON）：https://github.com/ClassIsland/ClassIsland
- ClassWidgets v1 schedule（JSON）：https://github.com/Class-Widgets/Class-Widgets
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yaml

_NAMESPACE = uuid.NAMESPACE_URL


def _uid(*parts) -> str:
    return str(uuid.uuid5(_NAMESPACE, "csespusher:" + ":".join(str(p) for p in parts)))


def _parse_hhmm(text: str) -> Optional[timedelta]:
    text = (text or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            t = datetime.strptime(text, fmt)
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except ValueError:
            continue
    return None


def _fmt_hms(td: timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return "%02d:%02d:%02d" % (h, m, s)


def _timeline_entries_for_day(timelines: dict, day: int, period_count: int) -> Optional[List[dict]]:
    """取某天的时间线条目。

    约定：同一天的时间流（上午/下午/晚自习）全部放在同一条时间线里，
    时间线代号 = 星期几（1=周一 … 7=周日）。
    兼容：若找不到对应代号但只有一条非空时间线，则所有天共用它。
    """
    key = str(int(day))
    if key in timelines and timelines[key]["entries"]:
        return sorted(timelines[key]["entries"],
                      key=lambda e: _parse_hhmm(e["start"]) or timedelta())
    non_empty = [tl for tl in timelines.values() if tl["entries"]]
    if len(non_empty) == 1:
        return sorted(non_empty[0]["entries"],
                      key=lambda e: _parse_hhmm(e["start"]) or timedelta())
    return None


def build_day_events(parsed: dict, cells: List[dict], day: int) -> Tuple[List[dict], Optional[str]]:
    """计算某一天从起点到终点的完整事件序列（含自动课间）。

    cells: 该班级该天的课位 [{"period":..,"subject_code":..}]
    返回 (events, 错误信息)。
    events: [{"type":"class"|"break","start":td,"end":td,"subject":name,"period":n}]
    """
    subjects_by_code = {s["code"]: s for s in parsed["subjects"]}
    periods = sorted({c["period"] for c in cells if c["day"] == day})
    entries = _timeline_entries_for_day(parsed["timelines"], day, len(periods))
    if entries is None:
        return [], "第 %d 天没有可用的时间线（或时间线条目不足以覆盖 %d 个课位）" % (day, len(periods))

    entries = sorted(entries, key=lambda e: _parse_hhmm(e["start"]) or timedelta())
    cells_by_period = {c["period"]: c for c in cells if c["day"] == day}

    events: List[dict] = []
    prev_end: Optional[timedelta] = None
    for i, entry in enumerate(entries):
        start = _parse_hhmm(entry["start"])
        if start is None:
            return [], "时间线第 %d 条开始时间无效：%r" % (i + 1, entry["start"])
        end = start + timedelta(minutes=entry["duration"])
        if prev_end is not None and start > prev_end:
            events.append({"type": "break", "start": prev_end, "end": start, "subject": None, "period": 0})
        cell = cells_by_period.get(periods[i]) if i < len(periods) else None
        if cell is not None:
            subject = subjects_by_code[cell["subject_code"]]
            subject_name = subject["name"]
        else:
            subject_name = entry.get("default_subject") or ""
        events.append({
            "type": "class", "start": start, "end": end,
            "subject": subject_name, "period": periods[i] if i < len(periods) else i + 1,
        })
        prev_end = end
    return events, None


# ---------------------------------------------------------------------------
# CSES v2 (YAML)
# ---------------------------------------------------------------------------

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def generate_cses(parsed: dict, school_name: str, grade_name: str, class_name: str,
                  cells: List[dict], school_id: int = 0) -> str:
    subject_seen = []
    for s in parsed["subjects"]:
        subject_seen.append(s)

    cses_subjects = []
    for s in subject_seen:
        item = {"name": s["name"]}
        if s.get("short_name"):
            item["simplified_name"] = s["short_name"]
        cses_subjects.append(item)

    schedules = []
    used_days = sorted({c["day"] for c in cells})
    for day in used_days:
        events, err = build_day_events(parsed, cells, day)
        if err:
            raise ValueError(err)
        classes = [
            {
                "subject": ev["subject"],
                "start_time": _fmt_hms(ev["start"]),
                "end_time": _fmt_hms(ev["end"]),
            }
            for ev in events
            if ev["type"] == "class" and ev["subject"]
        ]
        if classes:
            schedules.append({
                "name": DAY_NAMES[day - 1],
                "enable_day": [day] if day <= 5 else [day],
                "classes": classes,
            })

    doc = {
        "version": 2,
        "configuration": {
            "name": "%s %s %s 课程表" % (school_name, grade_name, class_name),
            "description": "由 csespusher 生成",
            "cycle": {
                "work_count": 5,
                "rest_count": 2,
                "spans": [
                    {"activity": "work", "count": 5},
                    {"activity": "rest", "count": 2},
                ],
            },
        },
        "subjects": cses_subjects,
        "schedules": schedules,
    }
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# ClassIsland profile (JSON)
# ---------------------------------------------------------------------------

def generate_classisland(parsed: dict, school_name: str, grade_name: str, class_name: str,
                         cells: List[dict], school_id: int) -> str:
    base = "ci:%d:%s:%s:%s" % (school_id, school_name, grade_name, class_name)

    subjects_out: Dict[str, dict] = {}
    code_to_guid: Dict[int, str] = {}
    for s in parsed["subjects"]:
        gid = _uid(base, "subject", s["code"])
        code_to_guid[s["code"]] = gid
        subjects_out[gid] = {
            "Name": s["name"],
            "Initial": s.get("short_name") or (s["name"][0] if s["name"] else ""),
            "TeacherName": "",
            "IsOutDoor": bool(s.get("outdoor")),
            "AttachedObjects": {},
        }

    time_layouts: Dict[str, dict] = {}
    class_plans: Dict[str, dict] = {}
    layout_cache: Dict[str, str] = {}

    for day in sorted({c["day"] for c in cells}):
        events, err = build_day_events(parsed, cells, day)
        if err:
            raise ValueError(err)
        if not events:
            continue

        layouts = []
        for ev in events:
            item = {
                "StartTime": _fmt_hms(ev["start"]),
                "EndTime": _fmt_hms(ev["end"]),
                "TimeType": 0 if ev["type"] == "class" else 1,
                "IsHideDefault": False,
                "DefaultClassId": "",
                "BreakName": "课间" if ev["type"] == "break" else None,
                "AttachedObjects": {},
                "IsActive": False,
            }
            layouts.append(item)

        sig = json.dumps([[e["type"], _fmt_hms(e["start"]), _fmt_hms(e["end"])] for e in events])
        if sig in layout_cache:
            layout_id = layout_cache[sig]
        else:
            layout_id = _uid(base, "layout", day)
            time_layouts[layout_id] = {"Name": DAY_NAMES[day - 1] + "时间表", "Layouts": layouts}
            layout_cache[sig] = layout_id

        subject_ids = []
        for ev in events:
            if ev["type"] != "class":
                continue
            match = [c for c in cells if c["day"] == day and c["period"] == ev["period"]]
            if match:
                subject_ids.append({"SubjectId": code_to_guid[match[0]["subject_code"]], "IsEnabled": True})
            else:
                subject_ids.append({"SubjectId": "", "IsEnabled": True})

        plan_id = _uid(base, "plan", day)
        class_plans[plan_id] = {
            "TimeLayoutId": layout_id,
            "TimeRule": {"WeekDay": day % 7, "WeekCountDiv": 0, "WeekCountDivTotal": 0},
            "Classes": subject_ids,
            "Name": DAY_NAMES[day - 1] + "课表",
            "IsEnabled": True,
            "AssociatedGroup": None,
        }

    profile = {
        "TimeLayouts": time_layouts,
        "ClassPlans": class_plans,
        "Subjects": subjects_out,
        "ClassPlanGroups": {},
        "OrderedSchedules": {},
        "IsOverlayClassPlanEnabled": False,
        "OverlayClassPlanId": None,
        "Name": "%s %s %s" % (school_name, grade_name, class_name),
    }
    return json.dumps(profile, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# ClassWidgets v1 schedule (JSON)
# ---------------------------------------------------------------------------

def generate_classwidgets(parsed: dict, school_name: str, grade_name: str, class_name: str,
                          cells: List[dict], school_id: int) -> str:
    part: Dict[str, list] = {}
    part_name: Dict[str, str] = {}
    timeline: Dict[str, list] = {"default": []}
    schedule: Dict[str, list] = {}
    for d in range(7):
        timeline[str(d)] = []
        schedule[str(d)] = []

    counter = {"class": 0, "break": 0}

    for day in sorted({c["day"] for c in cells}):
        events, err = build_day_events(parsed, cells, day)
        if err:
            raise ValueError(err)
        if not events:
            continue

        tl_key = str(day) if str(day) in parsed["timelines"] else None
        if tl_key:
            part_name[tl_key] = parsed["timelines"][tl_key]["name"]

        # ClassWidgets 键：0=周日 … 6=周六
        cw_day = str(day % 7)
        day_units = []
        day_subjects = []
        for ev in events:
            duration = int((ev["end"] - ev["start"]).total_seconds() // 60)
            if ev["type"] == "class":
                key = "a%d" % counter["class"]
                counter["class"] += 1
                part[key] = [duration // 60, duration % 60, "part"]
                day_units.append([0, key, len(day_subjects), duration])
                day_subjects.append(ev["subject"] or "")
            else:
                key = "f%d" % counter["break"]
                counter["break"] += 1
                part[key] = [duration // 60, duration % 60, "break"]
                day_units.append([1, key, 0, duration])
        timeline[cw_day] = day_units
        schedule[cw_day] = day_subjects

    doc = {
        "part": part,
        "part_name": part_name,
        "timeline": timeline,
        "timeline_even": {"default": []},
        "schedule": schedule,
        "schedule_even": {},
        "url": "local",
    }
    for d in range(7):
        doc["timeline_even"][str(d)] = []
        doc["schedule_even"][str(d)] = []
    return json.dumps(doc, ensure_ascii=False, indent=2)


GENERATORS = {
    "cses": (generate_cses, "yaml", "application/x-yaml"),
    "classisland": (generate_classisland, "json", "application/json"),
    "classwidgets": (generate_classwidgets, "json", "application/json"),
}
