# 每日热梗·生活资讯 · 云端推送 🚀

每天 **北京时间 10:00** 自动：

1. **采集**多平台实时热门内容
2. **生成**精美 HTML 页面（托管 GitHub Pages）
3. **推送**企微图文卡片，点击卡片打开网页查看完整内容

## ✨ 效果预览

**对话框里** —— 只收到一张精美卡片（带封面图 + 标题 + 一句话预览）
**点击打开** —— 跳转到深色主题的 HTML 详情页，包含 10 条精选 + 60 秒读世界

## 📦 内容构成（每日 10 条）

| 分类 | 条数 | 数据来源 |
|------|-----|---------|
| 🔥 热梗 | 3 | 微博 / 抖音 / 知乎 / B 站热搜（实时，自动过滤负面关键词） |
| 😄 冷笑话 | 2 | 60s 段子 API |
| 🎬 电影 | 2 | 猫眼实时票房 + 豆瓣每周榜 |
| 🎤 演唱会 | 1 | 按月份精选清单（脚本内维护） |
| 🧳 旅游 | 2 | 按月份精选季节性目的地 |

额外彩蛋：页面底部自动附带**今日 60 秒读懂世界**新闻。

## 🗂 项目结构

```
daily_push/
├── daily_push.py            # 核心脚本（采集 + HTML + 推送）
├── .github/workflows/
│   └── daily.yml            # GitHub Actions 定时任务
├── docs/                    # 生成的 HTML 页面（GitHub Pages 源）
│   ├── index.html           # 永远是最新一期
│   └── 2026-MM-DD.html      # 按日期归档
├── deploy_to_github.sh      # 一键推送到 GitHub
├── .gitignore
└── README.md
```

---

## 🚀 云端部署（推荐）

只需 4 步：

### 1. 创建 GitHub 仓库

去 <https://github.com/new> 创建一个仓库（public / private 均可，下文以 `daily-push` 为例）。

**不要**在创建时勾选 "Add a README"，保持空仓库。

### 2. 一键推送代码

```bash
cd /Users/hmd/Desktop/cursor/daily_push
bash deploy_to_github.sh git@github.com:<你的用户名>/daily-push.git
```

> 如果没有配置 SSH，可以用 HTTPS：`https://github.com/<你的用户名>/daily-push.git`

### 3. 配置 Secret（企微 Webhook）

进入仓库 → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|------|-------|
| `WEBHOOK_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<你的key>` |

### 4. 开启 GitHub Pages

进入仓库 → **Settings → Pages**：

- **Source**：Deploy from a branch
- **Branch**：`main`　**Folder**：`/docs`
- 点击 **Save**

保存后会显示 Pages 地址：`https://<你的用户名>.github.io/daily-push/`

### 5. 手动触发一次测试

进入仓库 → **Actions → Daily Push → Run workflow**

等待约 2 分钟，你的企微机器人会收到一张带封面图的精美卡片，点击即可在浏览器打开完整页面 🎉

---

## 🧪 本地调试

```bash
cd /Users/hmd/Desktop/cursor/daily_push

# 只生成 HTML（不推送），然后在浏览器预览
MODE=html python3 daily_push.py
open docs/index.html

# 完整流程（无 PAGES_URL 时自动降级为 markdown 推送）
python3 daily_push.py
```

## ⚙️ 自定义

### 修改推送时间

编辑 `.github/workflows/daily.yml` 中的 cron：

```yaml
schedule:
  - cron: "0 2 * * *"   # UTC 02:00 = 北京 10:00
                        # 改成 "30 0 * * *" 就是北京 08:30
```

### 修改演唱会 / 旅游清单

编辑 `daily_push.py` 中的 `CONCERTS_BY_MONTH` 和 `TRAVEL_BY_MONTH`，按月份更新当季热门。

### 调整每类条数

`main()` 里：

```python
"memes":    collect_memes(3),     # 热梗
"jokes":    collect_jokes(2),     # 冷笑话
"movies":   collect_movies(2),    # 电影
"concerts": collect_concerts(1),  # 演唱会
"travels":  collect_travel(2),    # 旅游
```

总和为 10，按需调整。

## 🔍 故障排查

- **没收到推送？** 进入 Actions 查看最近一次 run 的日志
- **图文卡片打不开？** 等 1-2 分钟让 Pages 完成部署；或检查 `PAGES_URL` 环境变量
- **封面图是灰色？** 某天 60s 封面 CDN 不稳定，脚本会自动 fallback 到 Unsplash

## 🧹 卸载本地 launchd（如果之前装过）

```bash
bash install.sh uninstall   # 旧版本遗留脚本
```

或手动：

```bash
launchctl unload ~/Library/LaunchAgents/com.hmd.dailypush.plist 2>/dev/null
rm ~/Library/LaunchAgents/com.hmd.dailypush.plist
```

## 📚 数据源致谢

- [60s-api](https://github.com/vikiboss/60s) — 聚合热搜 / 电影 / 段子
- GitHub Actions — 免费的定时任务托管
- GitHub Pages — 免费的静态页面托管
