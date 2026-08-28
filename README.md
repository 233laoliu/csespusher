# csespusher

CSES / ClassIsland / ClassWidgets 课程表配置分发平台。

为学校收集课程表（格式化 Excel），一键生成三种软件的配置文件，
管理员创建带 token 的分享链接分发到每个班级，学生打开链接即可下载导入。

## 功能

- **未登录用户（游客）**：主页按 省/市/校 分组浏览已收集学校；
  打开分享链接（带 token）可下载 CSES(.yaml) / ClassIsland(.json) / ClassWidgets(.json) 配置，
  页面内也可直接下载两款软件本体
- **普通管理员**：注册（邮箱+用户名）/ 验证码登录；创建学校、上传格式化 Excel、
  编辑杂项配置、多用户协作、创建/复制分享链接
- **超级管理员**：普通管理员的全部权限 + 用户管理 + 平台运行状态

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

杂项配置（config 的 AB/AC 列 + 管理页编辑）用于存放软件独有配置
（如 ClassIsland 主题、ClassWidgets 提示音），下载时以响应头 `X-Extra-Config-Keys` 附带键名。

## 目录结构

```
backend/
  app/
    main.py            # FastAPI 入口（自动建表、超管初始化、静态托管）
    models.py          # SQLAlchemy 模型
    routers/           # auth / admin / public / super
    excel_parser.py    # Excel 格式解析
    converters.py      # -> cses / classisland / classwidgets
frontend/
  src/views/           # Home / SharePage / Auth / Admin / Super ...
samples/               # 示例课程表
scripts/               # 示例生成脚本
```
