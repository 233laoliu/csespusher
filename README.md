# csespusher

CSES / ClassIsland / ClassWidgets 课程表配置分发平台。

为学校收集课程表（格式化 Excel），一键生成三种软件的配置文件，
管理员为每个班级生成固定分享链接与配置直链，学生打开即可下载导入。

## 功能

- **未登录用户（游客）**：主页按 省/市/校 分组浏览已收集学校；
  进入学校 → 点击班级即可查看课表预览，并下载三种格式配置；
  也可通过管理员分发的分享链接获取配置
- **普通管理员**：注册（邮箱+用户名）/ 验证码登录；创建学校、上传格式化 Excel、
  管理杂项配置（添加/编辑/删除/上传文件）、多用户协作、生成班级链接、
  为学校开启 NTP 时间同步（每日偏移 / 手动校准，对齐打铃）
- **超级管理员**：普通管理员的全部权限 + 用户管理 + 平台运行状态

## 链接体系

- **班级页面**（公开）：`/class/{班级id}` —— 课表预览 + 下载 + 配置直链
- **班级分享链接（固定唯一）**：`/share/{token}` —— 每个班级只有一个链接，
  管理员重复生成返回同一个；课程表更新后链接不变
- **配置直链（从互联网导入）**：
  `/api/public/classes/{班级id}/raw/{cses|classisland|classwidgets}`
  返回配置原文（带 CORS），可直接粘贴到软件「从互联网导入配置」功能中使用；
  链接固定，课表更新后无需更换

## 技术栈

- 后端：Python + FastAPI + SQLAlchemy + SQLite，openpyxl 解析 Excel
- 前端：Vue 3 + Vue Router + Vite，Fluent Design 风格
- 认证：邮箱+验证码登录（JWT），账号密码经 sha512 摘要存储

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
copy .env.example .env        # 按需修改，尤其是 SECRET_KEY 与超管邮箱
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8765
```

未配置 SMTP 时，登录验证码打印到后端控制台（开发模式）。
配置 `.env` 中的 `SMTP_*` 后即走真实邮件发送。

### 前端

```bash
cd frontend
npm install
npm run dev        # 开发：5173 端口，/api 代理到 8765
npm run build      # 构建到 frontend/dist，由后端自动托管（生产模式）
```

生产模式只需启动后端：访问 `http://127.0.0.1:8765/`。

## Excel 格式约定

- 每个非 `config` 的 sheet = 一个年级；行 1 从 B1 起填班级名；
  A 列从行 2 起填课位标记 `周几-第几节`（如 `周一-1`），
  同行 B 列起按班级顺序填 config 中的科目代号。
- `config` sheet：
  - A 列科目代号（行 2 起 1..n），B 列科目，C 列简称，D 列是否室外课（是/否）
  - E..Z 时间线区域：每条时间线占三列 —— 行 2 为名称、行 3 为代号（可选）、
    行 4 起每条 `<开始时间 hh:mm, 持续分钟, 默认课程>`；
    **同一天的时间流（上午/下午/晚自习）全部放在同一条时间线里**，
    时间线代号对应星期几（1=周一 … 7=周日）；
    条目之间的空闲时间自动视为课间；最多七条，留空不启用。
    兼容：若所有课表共用同一套时间表，只写一条时间线即可，未匹配的天自动回退到它
  - AB 列（行 2 起）为杂项配置名称，AC 列为内容（JSON 或纯文本）

示例文件：`samples/sample_timetable.xlsx`（由 `scripts/make_sample_xlsx.py` 生成）。

## 生成格式说明

- **CSES v2**（YAML）：符合 [SmartTeachCN/CSES](https://github.com/SmartTeachCN/CSES) schema，
  `subjects` + 每周一份 `schedules`（含自动计算的课间间隙由软件自行处理，仅输出课程点）
- **ClassIsland profile**（JSON）：GUID 字典结构（TimeLayouts/ClassPlans/Subjects），
  课间以 `TimeType=1` 插入时间线；导入后即为完整档案
- **ClassWidgets schedule**（JSON）：v1 格式（part / timeline / schedule），
  键 `0`..`6` 为周日..周六；配合软件内置导入使用

杂项配置（config 的 AB/AC 列）用于存放软件独有配置
（如 ClassIsland 主题、ClassWidgets 提示音），下载时以响应头 `X-Extra-Config-Keys` 附带键名。
管理员可在网页上添加 / 编辑 / 删除杂项配置，或直接上传 `.json/.txt/.yaml` 等配置文件作为配置值。

## NTP 时间同步（对齐学校打铃）

学校的打铃母钟往往每天固定走快/走慢若干秒，几周后铃声就和软件里的时间对不上。
为此每所学校可以开一个**独立的时间源**：

- 管理页 → 进入学校 → **「NTP 时间同步」卡片**：启用后自动分配端口
  （默认从 `11123` 起按学校顺序分配，可改），并实时显示当前偏差与学校时间；
- **每日偏移量**（秒/天，正负皆可）—— 学校时钟每天的漂移速度，系统按线性漂移持续累积；
- **手动校准** —— 对着学校时钟把表盘读数填进去，一键抹平累计误差，
  每日偏移量保持不变；也可「偏差清零」重新开始。

NTP 报文本身不带学校标识，所以**每校独占一个 UDP 端口**。
两条客户端途径，任选其一：

1. **NTP（UDP）**：把 `主机:端口` 填进支持自定义端口的时间同步客户端。
   校园 Linux/路由设备可用 chrony / ntpd：`server <主机> port <端口>`；
   Windows 自带的 w32time 只能连 123 端口——单校部署时把 `NTP_BASE_PORT` 改成
   `123` 即可原生使用，多校时用第三方客户端（NetTime、Meinberg NTP 等）。
2. **HTTP 校时**：`GET /api/public/ntp/{token}/time` 返回该校当前时间
   （`unix_ms` 已含偏移），供软件自行校表；地址在管理页与班级页可复制。

注意：

- 累计偏差很大时（ntp 客户端默认 panic 阈值 1000 秒），个别客户端会拒绝跳变，
  保持每日偏移在合理范围内并定期校准即可；
- 部署时记得放行 UDP 端口（Docker：`EXPOSE 11123-11378/udp`，
  运行时 `-p 11123-11378:11123-11378/udp`），反向代理后请配置 `NTP_PUBLIC_HOST`；
- 不需要此功能时设 `NTP_ENABLED=0`；多 worker 部署会端口冲突，请保持单进程；
- 改动会在管理页保存时立即生效，另有 `NTP_REFRESH_SECONDS` 周期兜底热更新；
- 可用 `scripts/ntp_selftest.py` 离线自检引擎（建临时库，不影响线上数据）。

## 目录结构

```
backend/
  app/
    main.py            # FastAPI 入口（自动建表、超管初始化、静态托管）
    models.py          # SQLAlchemy 模型
    ntp.py             # NTP 引擎：偏移计算 / 报文编解码 / 多端口 UDP 服务
    routers/           # auth / admin / public / super / ntp
    excel_parser.py    # Excel 格式解析
    converters.py      # -> cses / classisland / classwidgets
frontend/
  src/views/           # Home / SchoolPublic / ClassPublic / SharePage / Auth / Admin / Super
samples/               # 示例课程表
scripts/               # 示例生成脚本 / NTP 自检
```
