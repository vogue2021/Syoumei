# Syoumei · 証明台

面向留学申请的**多语种学历证明文书**在线生成工具。参考标准学历证明版式，一键生成「高中毕业证明 + 成绩证明」PDF，支持 5 种语言版本，开箱即用。

> `syoumei` 取自日语「証明」(しょうめい) 的罗马音 —— 证明、可信。

## ✨ 功能特性

- **5 种语言版本**：英语版、日语版、中文版、中英双语版、中日双语版
- **可视化成绩录入**：网页表单可新增 / 删除科目，自由填写 6 个学期成绩
- **智能字段联动**：切换语言后只显示该版本所需字段；英文 / 日文性别、she/he、her/his 依据中文性别自动推断
- **科目名多语言**：按所选版本自动切换中 / 英 / 日科目名，双语版以「中文 / 外文」并排呈现
- **在线预览**：生成前可先预览 PDF，所见即所得
- **用户反馈直达**：内置「联系作者」表单，经后端 Gmail SMTP 直发到作者邮箱

## 🧰 技术栈

- **前端**：纯静态 HTML / CSS / JS（无构建步骤），通过 `/api` 调用后端
- **后端**：[Flask](https://flask.palletsprojects.com/) 提供 `/api/generate`、`/api/feedback`、`/api/sample`
- **PDF**：[ReportLab](https://www.reportlab.com/)，PDF 在内存中生成并直接以二进制流返回（无需落盘）
- **部署形态**：[EdgeOne Pages](https://edgeone.ai/document/pages)（静态托管 + Python 云函数）

## 🚀 本地开发

### 1. 安装依赖

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量（用于反馈邮件，可选）

复制模板并填入你的 Gmail 应用专用密码：

```bash
cp .env.example .env
# 然后编辑 .env，填写 SMTP_USER / SMTP_PASS / FEEDBACK_TO
```

> `.env` 已被 `.gitignore` 忽略，密钥不会进入版本库。不配置也能正常生成 PDF，只是反馈表单不可用。

### 3. 启动本地服务

```bash
./run_web.sh
```

浏览器打开 `http://127.0.0.1:8765`，填写后点「预览 / 生成 PDF」，结果在页面内嵌预览并可直接下载。

## ☁️ 部署到 EdgeOne Pages

项目已按 EdgeOne Pages 约定组织，可直接在控制台导入仓库部署：

- **静态资源根目录**：仓库根目录（`index.html` 等）
- **构建命令**：无（纯静态，留空）
- **云函数**：`cloud-functions/api/[[default]].py`（Flask 入口，自动映射到 `/api/*`，平台会剥离 `/api` 前缀）
- **依赖**：`cloud-functions/requirements.txt`
- **环境变量**：在控制台配置 `SMTP_USER` / `SMTP_PASS` / `SMTP_HOST` / `SMTP_PORT` / `FEEDBACK_TO`（用于反馈邮件）

> 字体：Serverless（Linux）环境无 macOS 系统字体，已内置三级回退，最终回退到 ReportLab 自带 CID 字体
> （`STSong-Light` 中文、`HeiseiMin-W3` / `HeiseiKakuGo-W5` 日文，拉丁文用 `Times-Roman/Bold`），
> 无需附带任何字体文件即可正确渲染中日文。

## ⌨️ 命令行生成

编辑 `sample_data.json` 后执行：

```bash
python3 generator.py sample_data.json
```

指定输出路径：

```bash
python3 generator.py sample_data.json -o output/pdf/test.pdf
```

## 🗂️ 项目结构

```text
.
├── index.html                       # 静态前端（表单 / 预览 / 反馈，调用 /api）
├── app.py                           # 本地开发服务器（Flask：/ + /api，复用云函数代码）
├── generator.py                     # 命令行薄壳（复用云函数中的生成核心）
├── cloud-functions/
│   ├── requirements.txt             # 云函数依赖（flask、reportlab）
│   └── api/
│       ├── [[default]].py           # EdgeOne 云函数入口（Flask，映射 /api/*）
│       ├── service.py               # 路由 / 表单解析 / 反馈邮件
│       ├── generator.py             # PDF 生成核心（ReportLab，单一事实来源）
│       └── sample_data.json         # 后端默认值
├── sample_data.json                 # 示例数据 / 命令行输入
├── requirements.txt                 # 本地开发依赖
├── run_web.sh                       # 本地启动脚本
└── .env.example                     # 环境变量模板
```

> PDF 生成核心位于 `cloud-functions/api/generator.py`（云函数打包仅包含 `cloud-functions/` 内文件），
> 根目录 `generator.py` / `app.py` 通过 `sys.path` 复用同一份代码，避免重复维护。

## 📑 数据字段说明

`sample_data.json` 的 `language_mode` 可设为：

| 值 | 版本 |
|------|--------|
| `en` | 英语版 |
| `ja` | 日语版 |
| `zh` | 中文版 |
| `zh_en` | 中英双语版 |
| `zh_ja` | 中日双语版 |

`subjects` 为科目数组，每个科目包含：

- `name` / `name_en` / `name_ja` / `name_zh`：科目名（总名与各语言名）
- `g1_t1` ~ `g3_t2`：三个学年、每学年两个学期（前期 / 后期）的成绩

空字符串会留空，`/` 会显示为斜杠。

## 🔒 安全说明

- SMTP 密钥**仅从环境变量读取**，代码零硬编码，`.env` 不进 Git。
- 反馈接口对类型做白名单校验，对联系方式 / 类型做邮件头注入过滤，内容限长 5000 字。
- Gmail 需开启两步验证并使用**应用专用密码**，不能用账号登录密码。

## 📄 License

MIT
