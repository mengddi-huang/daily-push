#!/usr/bin/env python3
"""
每日热梗·生活资讯推送（云端版）
================================
1. 采集多平台热梗 / 冷笑话 / 电影 / 演唱会 / 旅游
2. 渲染为美观的 HTML 页面（输出到 docs/）
3. 推送企业微信图文卡片，点击跳转到 HTML 详情页

环境变量：
  WEBHOOK_URL  企微机器人 Webhook（必填，推送模式）
  PAGES_URL    HTML 托管根地址（云端模式必填），如：
                 https://<user>.github.io/<repo>
  MODE         html | push | all（默认 all）
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_API = "https://60s.viki.moe/v2"
HTTP_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)

ROOT = Path(__file__).resolve().parent
DOCS_DIR = ROOT / "docs"
LOG_PATH = ROOT / "push.log"

DEFAULT_WEBHOOK = (
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
    "?key=3c332191-56c4-471a-afff-adc9f0aa4a53"
)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or DEFAULT_WEBHOOK
PAGES_URL = (os.environ.get("PAGES_URL") or "").rstrip("/")
MODE = os.environ.get("MODE", "all").lower()

FALLBACK_COVER = (
    "https://images.unsplash.com/photo-1504608524841-42fe6f032b4b"
    "?auto=format&fit=crop&w=1068&h=455&q=80"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("daily_push")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_get_json(path: str) -> dict[str, Any] | None:
    url = f"{BASE_API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("code") != 200:
            log.warning("API %s code=%s", path, payload.get("code"))
            return None
        return payload.get("data")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("API %s failed: %s", path, exc)
        return None


def http_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Content collectors
# ---------------------------------------------------------------------------

SERIOUS_KEYWORDS = (
    "死", "亡", "遇难", "坠", "判", "枪", "爆炸", "地震", "海啸",
    "虐", "凶", "命案", "遗骸", "战争", "空袭", "袭击", "重伤",
    "命丧", "灾", "病逝", "疫情", "癌症", "自杀", "被杀", "杀害",
)


def _is_fun(title: str) -> bool:
    return bool(title) and not any(k in title for k in SERIOUS_KEYWORDS)


# ---- 热搜分类关键词 ----------------------------------------------------
# 顺序代表优先级：先匹配上的分类即为该条归属。
HOT_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("🤖 科技与 AI", (
        "AI", "ai", "大模型", "GPT", "ChatGPT", "OpenAI", "Claude", "Gemini",
        "Sora", "智谱", "DeepSeek", "豆包", "字节", "谷歌", "微软",
        "苹果", "iPhone", "iPad", "Mac", "库克", "华为", "小米", "汽车",
        "特斯拉", "马斯克", "芯片", "机器人", "算力", "量子", "算法",
        "程序员", "代码", "编程", "科技", "科学家", "研究",
    )),
    ("🎭 娱乐与明星", (
        "周杰伦", "林俊杰", "汪苏泷", "许嵩", "王力宏", "陈奕迅", "薛之谦",
        "明星", "演员", "艺人", "歌手", "演唱会", "巡演", "综艺",
        "电视剧", "电影", "剧", "网红", "主播", "直播", "出道", "官宣",
        "CP", "恋情", "结婚", "离婚", "分手", "粉丝", "偶像", "流量",
        "娱乐圈", "红毯", "颁奖", "选秀", "偶像",
    )),
    ("⚽ 体育赛事", (
        "足球", "篮球", "乒乓", "羽毛球", "世界杯", "亚洲杯", "奥运",
        "NBA", "CBA", "欧冠", "英超", "西甲", "德甲", "亚冠", "冠军",
        "夺冠", "决赛", "半决赛", "联赛", "国足", "国乒", "梅西", "C罗",
    )),
    ("🎮 游戏与二次元", (
        "游戏", "原神", "星穹铁道", "崩坏", "王者荣耀", "英雄联盟", "LOL",
        "LPL", "DOTA", "Steam", "Switch", "手游", "主机", "电竞",
        "动漫", "漫画", "二次元", "番剧", "原神", "鸣潮",
    )),
    ("💰 商业与财经", (
        "股", "A 股", "基金", "房价", "楼市", "房产", "经济", "财经",
        "投资", "上市", "退市", "破产", "融资", "IPO", "收购", "并购",
        "CEO", "创始人", "首富", "老板", "员工", "裁员", "加薪", "年终奖",
        "996", "工资", "薪资", "GDP", "消费", "通胀",
    )),
    ("🍜 美食与生活", (
        "美食", "餐厅", "零食", "奶茶", "咖啡", "外卖", "霸王茶姬",
        "瑞幸", "星巴克", "海底捞", "减肥", "健身", "瑜伽", "穿搭",
        "美妆", "护肤", "时尚", "育儿", "教育", "考研", "高考", "中考",
        "就业", "求职", "面试", "上班", "健康", "养生", "睡眠",
    )),
    ("🏛 时事与社会", (
        "政策", "国家", "中央", "部长", "市长", "总理", "总统", "外交",
        "国际", "新规", "法律", "法案", "通胀", "关税", "制裁", "协议",
        "会议", "访问", "签署", "发布", "启动",
    )),
    ("🌏 旅行与地理", (
        "旅游", "旅行", "景区", "樱花", "油菜花", "花海", "日落", "日出",
        "看海", "爬山", "徒步", "露营", "出差", "机票", "酒店", "民宿",
        "攻略", "穷游", "自驾",
    )),
]


def _classify(title: str) -> str:
    for cat, keys in HOT_CATEGORIES:
        if any(k in title for k in keys):
            return cat
    return "💬 其他话题"


def collect_hot_by_category() -> dict[str, list[dict[str, str]]]:
    """抓取微博/抖音/小红书/B 站热搜各前 20，去重后按分类组织。"""
    sources = [
        ("/weibo", "微博"),
        ("/douyin", "抖音"),
        ("/rednote", "小红书"),
        ("/bili", "B 站"),
    ]
    seen_titles: set[str] = set()
    buckets: dict[str, list[dict[str, str]]] = {}
    # 预先占位，保证分类顺序稳定
    for cat, _ in HOT_CATEGORIES:
        buckets[cat] = []
    buckets["💬 其他话题"] = []

    for path, label in sources:
        data = http_get_json(path)
        if not isinstance(data, list):
            continue
        for item in data[:20]:
            title = (item.get("title") or "").strip()
            if not title or title in seen_titles or not _is_fun(title):
                continue
            # 简易去重：标题完全一样 → 跳过
            seen_titles.add(title)
            cat = _classify(title)
            buckets[cat].append({
                "title": title,
                "source": label,
                "link": item.get("link") or "",
            })

    # 每个分类限制最多 6 条，避免展示过长；去掉空分类
    out: dict[str, list[dict[str, str]]] = {}
    for cat, items in buckets.items():
        if items:
            out[cat] = items[:6]
    return out


def collect_jokes(limit: int = 10) -> list[str]:
    jokes: list[str] = []
    seen: set[str] = set()
    for _ in range(limit * 3):
        data = http_get_json("/duanzi")
        if isinstance(data, dict):
            text = (data.get("duanzi") or "").strip()
            if text and text not in seen:
                seen.add(text)
                jokes.append(text)
        if len(jokes) >= limit:
            break

    fallback = [
        "我闺蜜减肥成功后，前男友想复合。她冷冷地说：当初你嫌我重，现在我轻了，但你更轻。",
        "老板说今年业绩不好，年终奖发不了。我说没事，我年初就没指望。老板愣了一下：那明年你也别指望了。",
        "朋友问我为什么不谈恋爱，我说我对自己要求很高。她点点头：嗯，你这要求确实太高了，一般人达不到。",
        "我妈让我找对象要门当户对，于是我找了个像我一样没对象的。",
        "我跟同事说我精神状态不好，他安慰我：没事，大家精神状态都不好，大家都在硬撑。这话听完我觉得更不好了。",
        "昨天买了一支贵得离谱的口红，今天早上出门戴了口罩，感觉像是花钱买了个心理安慰。",
        "我问 AI：怎样才能更自律？AI 说：建议你关掉手机。我想了想，关掉了 AI。",
        "最近终于攒了点钱，决定奖励自己。然后看了眼余额，决定继续批评自己。",
        "室友今天买了一束花放桌上，我以为他恋爱了。一问才知道是自己送给自己的——他说花会谢，人不一定会来。",
        "早上挤地铁，前面一个人突然回头对我笑。我还没反应过来，他说：兄弟，你踩我脚了，已经两站。",
    ]
    while len(jokes) < limit:
        pick = random.choice(fallback)
        if pick not in seen:
            seen.add(pick)
            jokes.append(pick)
    return jokes[:limit]


# ---- 影音 -------------------------------------------------------------------

def _parse_douban_item(d: dict[str, Any], kind: str) -> dict[str, str]:
    name = (d.get("title") or "").strip()
    subtitle_parts = (d.get("card_subtitle") or "").split("/")
    meta = (
        " / ".join(s.strip() for s in subtitle_parts[2:4])
        if len(subtitle_parts) >= 4 else ""
    )
    return {
        "kind": kind,
        "title": name,
        "subtitle": f"豆瓣 {d.get('rating', '-')}",
        "meta": meta,
        "cover": d.get("cover_proxy") or d.get("cover") or "",
        "link": d.get("url") or f"https://www.douban.com/search?q={urllib.parse.quote(name)}",
    }


def collect_media() -> dict[str, list[dict[str, str]]]:
    """
    返回影音三类：movies / tvs / musics
    - 电影：豆瓣每周榜 top 3
    - 电视剧：国产 + 全球各 2 部
    - 音乐：网易云飙升榜 top 5
    """
    media: dict[str, list[dict[str, str]]] = {"movies": [], "tvs": [], "musics": []}

    movies = http_get_json("/douban/weekly/movie") or []
    if isinstance(movies, list):
        for d in movies[:3]:
            media["movies"].append(_parse_douban_item(d, "🎬 电影"))

    tv_cn = http_get_json("/douban/weekly/tv_chinese") or []
    if isinstance(tv_cn, list):
        for d in tv_cn[:2]:
            media["tvs"].append(_parse_douban_item(d, "📺 国产剧"))

    tv_gl = http_get_json("/douban/weekly/tv_global") or []
    if isinstance(tv_gl, list):
        for d in tv_gl[:2]:
            media["tvs"].append(_parse_douban_item(d, "📺 海外剧"))

    # 网易云飙升榜 (ID 19723756) ——最能代表当下流行趋势
    ncm = http_get_json("/ncm-rank/19723756") or []
    if isinstance(ncm, list):
        for s in ncm[:5]:
            artists = s.get("artist") or []
            artist_names = " / ".join(a.get("name", "") for a in artists if a.get("name"))
            album = (s.get("album") or {}).get("name", "")
            media["musics"].append({
                "kind": "🎵 流行音乐",
                "title": s.get("title") or "",
                "subtitle": f"{artist_names}",
                "meta": f"专辑《{album}》" if album else "",
                "cover": (s.get("album") or {}).get("cover", ""),
                "link": s.get("link") or "",
            })

    return media


def get_daily_news() -> list[dict[str, str]]:
    """
    返回 60 秒每日新闻，每条是 {text, link}
    点击后跳转到百度搜索该新闻关键词。
    """
    data = http_get_json("/60s") or {}
    raw = data.get("news") or []
    out: list[dict[str, str]] = []
    for text in raw:
        # 提取前 20 字作为搜索关键词（去掉开头的数字年份等）
        cleaned = text.split("，", 1)[0].split("：", 1)[0]
        kw = cleaned[:20]
        out.append({
            "text": text,
            "link": f"https://www.baidu.com/s?wd={urllib.parse.quote(kw)}&tn=news",
        })
    return out


# ---------------------------------------------------------------------------
# 演唱会：重点艺人列表（用户偏好）
# ---------------------------------------------------------------------------

FAVORITE_ARTISTS: list[dict[str, str]] = [
    {"name": "汪苏泷", "tag": "情歌诗人", "style": "流行/情歌"},
    {"name": "许嵩",   "tag": "V 仙级创作歌手", "style": "中国风 / 创作"},
    {"name": "徐良",   "tag": "非主流时代经典", "style": "情歌 / 复古"},
    {"name": "王力宏", "tag": "华语 R&B 代表", "style": "R&B / 抒情"},
    {"name": "周杰伦", "tag": "华语天王", "style": "流行 / 经典"},
    {"name": "陈粒",   "tag": "小众清新派", "style": "民谣 / 独立"},
    {"name": "李荣浩", "tag": "全能唱作人", "style": "流行 / 都市"},
    {"name": "林俊杰", "tag": "JJ20 FINAL LAP 尾声", "style": "流行 / 抒情"},
    {"name": "告五人", "tag": "金曲台独立乐团", "style": "独立 / 现场"},
]


def collect_concerts(limit: int = 5) -> list[dict[str, str]]:
    """
    每天随机挑 N 位主要艺人，给出大麦网搜索链接（点击看最新场次）。
    """
    picks = random.sample(FAVORITE_ARTISTS, k=min(limit, len(FAVORITE_ARTISTS)))
    out = []
    for a in picks:
        kw = f"{a['name']} 演唱会"
        out.append({
            "artist": a["name"],
            "tag": a["tag"],
            "style": a["style"],
            "link": f"https://search.damai.cn/search.html?keyword={urllib.parse.quote(kw)}",
        })
    return out


# ---------------------------------------------------------------------------
# 旅游：按月份推荐，每条含目的地、季节理由、深圳出发交通
# 距离深圳 <= 3 小时优先；季节限定强的也会纳入
# ---------------------------------------------------------------------------

TRAVEL_BY_MONTH: dict[int, list[dict[str, str]]] = {
    1: [
        {
            "name": "哈尔滨·冰雪大世界",
            "season": "隆冬冰雕最盛期，零下 20℃ 的极致雪国体验",
            "access": "深圳宝安 → 哈尔滨直飞约 5h；冰雪大世界在市区打车可达",
            "duration": "4-5 天",
        },
        {
            "name": "广东韶关·丹霞山",
            "season": "冬日山体赤红分明，云海雾凇偶尔可遇",
            "access": "深圳北 → 韶关 高铁 1h30；景区打车 30 分钟",
            "duration": "2 天 1 晚",
        },
        {
            "name": "海南三亚·后海",
            "season": "全国最暖冬日海滨，冲浪水温 22℃",
            "access": "深圳宝安 → 三亚凤凰 1h40；打车至后海 1h",
            "duration": "3-4 天",
        },
    ],
    2: [
        {
            "name": "广东云浮·罗浮山 + 温泉",
            "season": "早春山茶花开，山脚温泉最宜泡",
            "access": "深圳北 → 惠州南 高铁 30 分钟，自驾 / 包车入山",
            "duration": "2 天 1 晚",
        },
        {
            "name": "厦门·鼓浪屿",
            "season": "春节南下避寒，气温 15-20℃，海岛文艺氛围",
            "access": "深圳北 → 厦门北 高铁 3h30；或直飞 1h30",
            "duration": "3 天",
        },
        {
            "name": "云南元阳·哈尼梯田",
            "season": "冬末灌水期，日出云海最为壮观",
            "access": "深圳宝安 → 昆明 2h，转高铁至建水 2h，包车入梯田",
            "duration": "4-5 天",
        },
    ],
    3: [
        {
            "name": "江西婺源·油菜花",
            "season": "3 月下旬全国最经典的金色花海盛期",
            "access": "深圳北 → 婺源 高铁 6h；或飞南昌转高铁 3h",
            "duration": "3-4 天",
        },
        {
            "name": "广东惠州·巽寮湾",
            "season": "春海气温回暖，水清沙白适合家庭短途",
            "access": "深圳 → 巽寮湾 自驾 2h；或包车",
            "duration": "2 天 1 晚",
        },
        {
            "name": "福建漳州·东山岛",
            "season": "3 月海风温柔，日落金黄色最上镜",
            "access": "深圳北 → 潮汕站 高铁 1h20 + 自驾 1h30 到东山",
            "duration": "3 天",
        },
    ],
    4: [
        {
            "name": "广西阳朔·漓江 + 遇龙河",
            "season": "4 月春雨过后山水最润，竹筏皮划艇黄金期",
            "access": "深圳北 → 桂林 高铁 3h30；阳朔打车 1h20",
            "duration": "3 天 2 晚",
            "why_sz": "距离深圳最近的春日山水之一，整周末往返可行",
        },
        {
            "name": "江西龙虎山 + 武夷山双程",
            "season": "清明前后春茶季开采，丹霞绿水对比强烈",
            "access": "深圳北 → 武夷山东 高铁 5h30；或直飞武夷山 1h40",
            "duration": "4-5 天",
            "why_sz": "广东出发最方便的春茶行程",
        },
        {
            "name": "湖南张家界·国家森林公园",
            "season": "谷雨后新绿，云雾山景如水墨",
            "access": "深圳宝安 → 张家界荷花 1h50；景区大巴 30 分钟",
            "duration": "4 天",
            "why_sz": "直飞航班多，票价友好",
        },
        {
            "name": "新疆伊犁·杏花沟",
            "season": "4 月中下旬限定·粉色杏花海仅 10 天花期",
            "access": "深圳宝安 → 伊宁 直飞约 6h；包车入沟 1h",
            "duration": "7-8 天",
            "why_sz": "远但值得，需要提前订机票",
        },
        {
            "name": "河南洛阳·牡丹花会",
            "season": "谷雨前后牡丹盛开，千年国花传统",
            "access": "深圳北 → 洛阳龙门 高铁 6h；或飞郑州 2h20 转高铁",
            "duration": "3-4 天",
            "why_sz": "可与龙门石窟、少林寺一起安排",
        },
    ],
    5: [
        {
            "name": "青海湖 + 茶卡盐湖",
            "season": "5 月起天空之镜开放，人少景美",
            "access": "深圳 → 西宁 直飞 4h；包车环湖 3 天",
            "duration": "5-6 天",
        },
        {
            "name": "广东南岭·徒步",
            "season": "五一前后高山杜鹃盛花期",
            "access": "深圳北 → 韶关 高铁 1h30 + 自驾 1h 入山",
            "duration": "2 天 1 晚",
        },
        {
            "name": "四川稻城亚丁",
            "season": "五一草甸返青，雪山清晰度全年最佳",
            "access": "深圳 → 成都 2h40，转机至亚丁机场 1h",
            "duration": "5-7 天",
        },
    ],
    6: [
        {
            "name": "内蒙古·呼伦贝尔大草原",
            "season": "6 月草原返青，夜晚可睡星空房",
            "access": "深圳 → 海拉尔 经停 1 次 6h；包车环线",
            "duration": "6-7 天",
        },
        {
            "name": "广东惠州·双月湾",
            "season": "初夏海水温度最适合浮潜",
            "access": "深圳 → 双月湾 自驾 2h20",
            "duration": "2 天 1 晚",
        },
    ],
    7: [
        {
            "name": "新疆伊犁·薰衣草 + 喀拉峻草原",
            "season": "盛夏限定·薰衣草花海 + 高原湿润草甸",
            "access": "深圳宝安 → 伊宁 直飞 6h；包车环线 5 天",
            "duration": "7-8 天",
        },
        {
            "name": "贵州·荔波小七孔",
            "season": "7 月水量最大，喀斯特翡翠瀑布最美",
            "access": "深圳北 → 贵阳 高铁 5h30；或直飞 2h；转动车至荔波",
            "duration": "3-4 天",
        },
    ],
    8: [
        {
            "name": "川西·色达 + 稻城亚丁",
            "season": "盛夏高原凉爽 20℃，雪山草原并存",
            "access": "深圳 → 成都 2h40，包车走川西环线",
            "duration": "7-9 天",
        },
        {
            "name": "新疆·喀纳斯 + 禾木",
            "season": "童话秋初序章，湖水蓝得不真实",
            "access": "深圳 → 乌鲁木齐 5h30，转机至喀纳斯 1h",
            "duration": "6-7 天",
        },
    ],
    9: [
        {
            "name": "新疆·北疆大环线（金秋序章）",
            "season": "9 月下旬金秋第一缕，避开旺季",
            "access": "深圳 → 乌鲁木齐 直飞 5h30；租车自驾",
            "duration": "8-10 天",
        },
        {
            "name": "西藏·林芝 + 然乌湖",
            "season": "秋日转山转水，天高云淡",
            "access": "深圳 → 拉萨 中转 7-8h；或广州直飞林芝",
            "duration": "6-8 天",
        },
    ],
    10: [
        {
            "name": "新疆·喀纳斯金秋",
            "season": "10 月初金秋盛期，童话色彩最浓",
            "access": "深圳 → 乌鲁木齐 5h30 + 转喀纳斯 1h",
            "duration": "6-7 天",
        },
        {
            "name": "广东连州·地下河 + 小北江",
            "season": "国庆后错峰，山林秋色 + 喀斯特河谷",
            "access": "深圳北 → 连州 高铁 3h",
            "duration": "3 天",
        },
        {
            "name": "内蒙古·额济纳胡杨林",
            "season": "10 月中下旬金色限定·中国最壮阔的秋色",
            "access": "深圳 → 额济纳机场 中转 8h；建议跟团",
            "duration": "5-6 天",
        },
    ],
    11: [
        {
            "name": "云南·腾冲银杏村",
            "season": "11 月中下旬限定金黄，古村 + 火山温泉",
            "access": "深圳 → 腾冲 直飞 3h；或飞昆明转机",
            "duration": "4-5 天",
        },
        {
            "name": "广东梅州·雁南飞 + 客家围屋",
            "season": "初冬柚子成熟，客家美食季",
            "access": "深圳北 → 梅州西 高铁 3h10",
            "duration": "2-3 天",
        },
    ],
    12: [
        {
            "name": "哈尔滨·冰雪大世界（首开）",
            "season": "12 月下旬开园，跨年首选",
            "access": "深圳 → 哈尔滨直飞 5h",
            "duration": "4-5 天",
        },
        {
            "name": "海南·万宁日月湾冲浪",
            "season": "冬日浪况最佳，水温 24℃",
            "access": "深圳 → 三亚 1h40，转日月湾包车 2h",
            "duration": "4-5 天",
        },
        {
            "name": "广东从化·温泉 + 流溪河森林公园",
            "season": "冬日温泉季，深圳出发最近的温泉",
            "access": "深圳 → 从化 自驾 2h；或高铁至广州转车",
            "duration": "2 天 1 晚",
        },
    ],
}


def collect_travel(limit: int = 3) -> list[dict[str, str]]:
    pool = TRAVEL_BY_MONTH.get(datetime.now().month, [])
    picks = random.sample(pool, k=min(limit, len(pool))) if pool else []
    out = []
    for p in picks:
        kw = p["name"].split("·", 1)[0].strip()
        out.append({
            **p,
            "link": f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(kw + ' 攻略')}&source=web_search_result_notes",
        })
    return out


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def e(text: str) -> str:
    return html_mod.escape(text or "", quote=True)


def _link_or_span(href: str, inner_html: str, extra_class: str = "") -> str:
    """有 link 就包 <a>（可点击），否则包 <div>（静态）。"""
    cls = f"row {extra_class}".strip()
    if href:
        return (
            f'<a class="{cls}" href="{e(href)}" target="_blank" rel="noopener">'
            f'{inner_html}<span class="chev" aria-hidden="true">›</span>'
            "</a>"
        )
    return f'<div class="{cls} static">{inner_html}</div>'


def render_html(ctx: dict[str, Any]) -> str:
    date: datetime = ctx["date"]
    weekday = "一二三四五六日"[date.weekday()]
    date_str = f"{date:%Y 年 %m 月 %d 日} · 星期{weekday}"

    # ---- 分类热搜 ----
    hot_blocks = []
    for cat, items in (ctx["hot"] or {}).items():
        rows = []
        for i, m in enumerate(items, 1):
            inner = (
                f'<span class="rank">{i:02d}</span>'
                '<div class="main">'
                f'<div class="title">{e(m["title"])}</div>'
                f'<div class="sub">{e(m["source"])}</div>'
                '</div>'
            )
            rows.append(_link_or_span(m.get("link", ""), inner, "meme"))
        hot_blocks.append(
            f'<div class="cat-group">'
            f'  <div class="cat-title">{e(cat)}<span class="cat-count">{len(items)}</span></div>'
            f'  {"".join(rows)}'
            f'</div>'
        )
    hot_section = "".join(hot_blocks) if hot_blocks else "<div class=\"row static\"><div class=\"main\"><div class=\"title\">今日热搜暂未抓取到</div></div></div>"

    # ---- 冷笑话 ----
    joke_items = "\n".join(f'<div class="joke">{e(j)}</div>' for j in ctx["jokes"])

    # ---- 影音（电影+电视剧+音乐）----
    def _render_media_row(m: dict[str, str]) -> str:
        poster = (
            f'<img src="{e(m["cover"])}" alt="" class="poster" loading="lazy">'
            if m.get("cover") else '<div class="poster poster-empty">♪</div>'
        )
        meta = f'<div class="meta">{e(m["meta"])}</div>' if m.get("meta") else ""
        inner = (
            f'{poster}'
            '<div class="main">'
            f'<div class="title">{e(m["title"])}</div>'
            f'<div class="sub"><span class="accent">{e(m["subtitle"])}</span></div>'
            f'{meta}'
            f'<div class="tag">{e(m["kind"])}</div>'
            '</div>'
        )
        return _link_or_span(m.get("link", ""), inner, "movie")

    media = ctx["media"] or {}
    all_media = (media.get("movies") or []) + (media.get("tvs") or []) + (media.get("musics") or [])
    media_items = "\n".join(_render_media_row(m) for m in all_media)

    # ---- 演唱会（主要艺人）----
    concert_rows = []
    for c in ctx["concerts"]:
        inner = (
            '<span class="dot concert-dot"></span>'
            '<div class="main">'
            f'<div class="title">{e(c["artist"])}<span class="chip">{e(c["tag"])}</span></div>'
            f'<div class="sub">{e(c["style"])} · 大麦网搜索最新场次</div>'
            '</div>'
        )
        concert_rows.append(_link_or_span(c.get("link", ""), inner, "concert"))
    concert_items = "\n".join(concert_rows)

    # ---- 旅游（详细版）----
    travel_rows = []
    for t in ctx["travels"]:
        why_sz = f'<div class="meta sz">深圳视角：{e(t["why_sz"])}</div>' if t.get("why_sz") else ""
        inner = (
            '<span class="dot travel-dot"></span>'
            '<div class="main">'
            f'<div class="title">{e(t["name"])}</div>'
            f'<div class="sub"><span class="accent">✦ {e(t["season"])}</span></div>'
            f'<div class="meta">🚄 {e(t["access"])}</div>'
            f'<div class="meta">⏱ 建议 {e(t.get("duration", ""))}</div>'
            f'{why_sz}'
            '</div>'
        )
        travel_rows.append(_link_or_span(t.get("link", ""), inner, "travel"))
    travel_items = "\n".join(travel_rows)

    # ---- 60 秒读世界（可点击跳百度搜索）----
    news_rows = []
    for n in (ctx["news"] or [])[:10]:
        inner = (
            '<span class="news-bullet"></span>'
            f'<div class="main"><div class="title news-title">{e(n["text"])}</div></div>'
        )
        news_rows.append(_link_or_span(n.get("link", ""), inner, "news-row"))
    news_items = "\n".join(news_rows)

    generated = f"{datetime.now():%Y-%m-%d %H:%M}"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0d1424">
<title>每日热梗·{e(date.strftime('%Y-%m-%d'))}</title>
<style>
  :root {{
    --bg: #0d1424;
    --bg-soft: #151d33;
    --card: rgba(255,255,255,0.035);
    --card-border: rgba(255,255,255,0.07);
    --card-hover: rgba(255,255,255,0.06);
    --fg: #eef1f8;
    --fg-2: #b4bdd1;
    --fg-3: #7d879f;
    --accent: #ffb86b;
    --accent-soft: rgba(255,184,107,0.14);
    --hot: #ff7a7a;
    --mint: #6ddaa8;
    --sky: #82b1ff;
    --divider: rgba(255,255,255,0.06);
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    font: 15px/1.65 -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft Yahei", sans-serif;
    color: var(--fg);
    background: var(--bg);
    background-image:
      radial-gradient(800px 400px at -10% -10%, rgba(130, 177, 255, 0.08), transparent 60%),
      radial-gradient(600px 300px at 110% 0%, rgba(255, 184, 107, 0.06), transparent 60%);
    min-height: 100vh;
    padding: 20px 16px calc(60px + env(safe-area-inset-bottom));
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }}
  .wrap {{ max-width: 640px; margin: 0 auto; }}
  a {{ color: inherit; text-decoration: none; -webkit-tap-highlight-color: transparent; }}

  /* ========== Header ========== */
  header {{ padding: 4px 4px 16px; }}
  .brand {{
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; letter-spacing: 3px;
    color: var(--fg-3); text-transform: uppercase;
    padding: 4px 10px;
    border: 1px solid var(--card-border);
    border-radius: 20px;
  }}
  h1 {{
    margin: 14px 0 4px;
    font-size: 26px; font-weight: 800; letter-spacing: -0.5px;
    color: var(--fg);
  }}
  .date {{
    color: var(--fg-3); font-size: 13px;
    font-family: "SF Mono", "Menlo", monospace;
  }}
  /* ========== Section ========== */
  section {{
    margin-top: 22px;
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 4px 0;
    overflow: hidden;
  }}
  .sec-head {{
    display: flex; align-items: center;
    padding: 14px 18px 6px;
    gap: 10px;
  }}
  .sec-head h2 {{
    margin: 0;
    font-size: 13px; font-weight: 700;
    letter-spacing: 2px;
    color: var(--fg-2);
    text-transform: uppercase;
  }}
  .sec-head .count {{
    margin-left: auto;
    color: var(--fg-3); font-size: 12px;
    font-family: "SF Mono", "Menlo", monospace;
  }}

  /* ========== Row (可点击条目通用样式) ========== */
  .row {{
    display: flex; align-items: center; gap: 12px;
    padding: 14px 18px;
    border-top: 1px solid var(--divider);
    transition: background 0.18s ease;
    position: relative;
  }}
  .row:first-of-type {{ border-top: 1px solid var(--divider); }}
  .sec-head + .row {{ border-top: 1px solid var(--divider); }}
  a.row:hover,
  a.row:active {{ background: var(--card-hover); }}
  .row.static {{ cursor: default; }}
  .row .main {{ flex: 1; min-width: 0; }}
  .row .title {{
    font-weight: 600; font-size: 15px; color: var(--fg);
    line-height: 1.5; word-break: break-word;
  }}
  .row .sub {{
    margin-top: 3px;
    font-size: 12px; color: var(--fg-3);
  }}
  .row .sub .accent {{ color: var(--accent); font-weight: 600; }}
  .row .chev {{
    flex: 0 0 auto;
    color: var(--fg-3);
    font-size: 22px; line-height: 1;
    font-family: "SF Mono", "Menlo", monospace;
    opacity: 0.6;
    transition: transform 0.18s ease, opacity 0.18s ease;
  }}
  a.row:hover .chev {{ opacity: 1; transform: translateX(2px); color: var(--accent); }}

  /* ========== 热梗 ========== */
  .meme .rank {{
    flex: 0 0 28px;
    font-family: "SF Mono", "Menlo", monospace;
    font-weight: 700;
    font-size: 14px;
    color: var(--hot);
    letter-spacing: 0;
  }}

  /* ========== 冷笑话 ========== */
  .joke {{
    padding: 14px 18px;
    border-top: 1px solid var(--divider);
    color: var(--fg);
    font-size: 14.5px;
    line-height: 1.75;
    position: relative;
  }}
  .joke::before {{
    content: '"';
    display: inline-block;
    color: var(--accent);
    font-size: 28px;
    line-height: 0.8;
    margin-right: 6px;
    font-weight: 700;
    vertical-align: -8px;
  }}

  /* ========== 电影 ========== */
  .movie .poster {{
    flex: 0 0 64px;
    width: 64px; height: 88px;
    object-fit: cover;
    border-radius: 8px;
    background: var(--bg-soft);
    box-shadow: 0 4px 12px -4px rgba(0,0,0,0.5);
  }}
  .movie .poster-empty {{
    display: grid; place-items: center;
    color: var(--fg-3); font-size: 24px;
  }}
  .movie .main {{ display: flex; flex-direction: column; gap: 4px; min-height: 88px; }}
  .movie .title {{ font-size: 16px; font-weight: 700; }}
  .movie .meta {{ font-size: 12px; color: var(--fg-3); }}
  .movie .tag {{
    align-self: flex-start;
    margin-top: auto;
    padding: 2px 8px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 11px;
    border-radius: 999px;
    font-weight: 600;
  }}

  /* ========== 演唱会 & 旅游 ========== */
  .dot {{
    flex: 0 0 8px;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-left: 4px;
    margin-top: 10px;
    align-self: flex-start;
  }}
  .concert-dot {{ background: var(--sky); box-shadow: 0 0 10px rgba(130,177,255,0.5); }}
  .travel-dot  {{ background: var(--mint); box-shadow: 0 0 10px rgba(109,218,168,0.5); }}
  .chip {{
    display: inline-block;
    margin-left: 8px;
    padding: 1px 8px;
    border-radius: 999px;
    background: rgba(130,177,255,0.15);
    color: var(--sky);
    font-size: 11px;
    font-weight: 500;
    vertical-align: 2px;
  }}
  .meta {{ font-size: 12px; color: var(--fg-3); margin-top: 4px; line-height: 1.6; }}
  .meta.sz {{ color: var(--mint); }}

  /* ========== 分类热搜分组 ========== */
  .cat-group {{
    border-top: 1px solid var(--divider);
  }}
  .cat-group:first-of-type {{ border-top: 1px solid var(--divider); }}
  .cat-title {{
    padding: 14px 18px 8px;
    font-size: 13px;
    font-weight: 700;
    color: var(--fg-2);
    letter-spacing: 1px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .cat-count {{
    font-family: "SF Mono", "Menlo", monospace;
    font-size: 11px;
    color: var(--fg-3);
    background: rgba(255,255,255,0.05);
    padding: 1px 8px;
    border-radius: 999px;
    font-weight: 500;
  }}

  /* ========== 60 秒 ========== */
  .news-row .news-title {{
    font-weight: 500;
    color: var(--fg-2);
    font-size: 13.5px;
    line-height: 1.7;
  }}
  .news-bullet {{
    flex: 0 0 6px;
    width: 6px; height: 6px;
    background: var(--fg-3);
    border-radius: 50%;
    align-self: flex-start;
    margin-top: 10px;
  }}

  /* ========== Footer ========== */
  footer {{
    margin-top: 32px;
    text-align: center;
    color: var(--fg-3);
    font-size: 12px;
    line-height: 2;
    font-family: "SF Mono", "Menlo", monospace;
  }}
  footer .sources {{ color: var(--fg-3); }}
  footer a {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">Daily Digest</div>
    <h1>今日热梗 · 生活资讯</h1>
    <div class="date">{e(date_str)}</div>
  </header>

  <section>
    <div class="sec-head">
      <h2>🔥 今日热搜</h2>
      <div class="count">微博 · 抖音 · 小红书 · B 站 · 点击看原帖</div>
    </div>
    {hot_section}
  </section>

  <section>
    <div class="sec-head">
      <h2>😄 冷笑话</h2>
      <div class="count">{len(ctx["jokes"])} 条</div>
    </div>
    {joke_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>🎬 影音榜单</h2>
      <div class="count">电影 · 剧集 · 流行音乐 · 点击看详情</div>
    </div>
    {media_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>🎤 演唱会关注</h2>
      <div class="count">{len(ctx["concerts"])} 位 · 点击查大麦网最新场次</div>
    </div>
    {concert_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>🧳 旅游推荐</h2>
      <div class="count">{len(ctx["travels"])} 处 · 深圳出发视角 · 点击看攻略</div>
    </div>
    {travel_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>📰 60 秒读懂世界</h2>
      <div class="count">{len(ctx["news"] or [])} 条 · 点击搜索详情</div>
    </div>
    {news_items}
  </section>

  <footer>
    <div class="sources">微博 · 抖音 · 小红书 · B 站 · 豆瓣 · 网易云 · 60s</div>
    <div>生成于 {e(generated)} · <a href="./archive.html">📚 往期归档</a></div>
  </footer>
</div>
</body>
</html>
"""


def write_html_files(html: str, date: datetime) -> Path:
    """写入 docs/index.html + 归档 docs/YYYY-MM-DD.html + docs/archive.html 索引页。"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    archive = DOCS_DIR / f"{date:%Y-%m-%d}.html"
    index = DOCS_DIR / "index.html"
    archive.write_text(html, encoding="utf-8")
    index.write_text(html, encoding="utf-8")
    log.info("HTML 已生成: %s", archive.name)
    # 每次生成后更新归档索引
    write_archive_index()
    return index


def write_archive_index() -> None:
    """扫描 docs/ 下所有 YYYY-MM-DD.html，生成归档列表页 archive.html。"""
    import re as _re
    entries: list[str] = []
    pattern = _re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
    dates: list[str] = []
    for p in sorted(DOCS_DIR.glob("*.html"), reverse=True):
        m = pattern.match(p.name)
        if not m:
            continue
        d = m.group(1)
        dates.append(d)
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            weekday = "一二三四五六日"[dt.weekday()]
            label = f"{dt:%Y 年 %m 月 %d 日}"
            sub = f"星期{weekday}"
        except ValueError:
            label, sub = d, ""
        entries.append(
            f'<a class="arch-row" href="./{d}.html">'
            f'<div class="main">'
            f'<div class="title">{label}</div>'
            f'<div class="sub">{sub}</div>'
            f'</div><span class="chev">›</span></a>'
        )

    if not entries:
        entries.append(
            '<div class="arch-row static"><div class="main">'
            '<div class="title">暂无归档</div></div></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0d1424">
<title>每日热梗 · 往期归档</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font: 15px/1.6 -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft Yahei", sans-serif;
    background: #0d1424;
    color: #eef1f8;
    background-image:
      radial-gradient(800px 400px at -10% -10%, rgba(130,177,255,0.08), transparent 60%),
      radial-gradient(600px 300px at 110% 0%, rgba(255,184,107,0.06), transparent 60%);
    min-height: 100vh;
    padding: 28px 16px 80px;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 640px; margin: 0 auto; }}
  a {{ color: inherit; text-decoration: none; }}
  .brand {{
    display: inline-block;
    font-size: 11px; letter-spacing: 3px;
    color: #7d879f; text-transform: uppercase;
    padding: 4px 10px;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
  }}
  h1 {{ margin: 14px 0 4px; font-size: 26px; font-weight: 800; }}
  .sub-top {{ color: #7d879f; font-size: 13px; margin-bottom: 24px; }}
  .back {{
    display: inline-flex; align-items: center; gap: 6px;
    color: #ffb86b; font-size: 13px;
    margin-bottom: 20px;
  }}
  .list {{
    background: rgba(255,255,255,0.035);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    overflow: hidden;
  }}
  .arch-row {{
    display: flex; align-items: center; gap: 10px;
    padding: 16px 18px;
    border-top: 1px solid rgba(255,255,255,0.06);
    transition: background 0.18s ease;
  }}
  .arch-row:first-child {{ border-top: none; }}
  a.arch-row:hover {{ background: rgba(255,255,255,0.06); }}
  .arch-row .main {{ flex: 1; }}
  .arch-row .title {{ font-weight: 600; font-size: 15px; }}
  .arch-row .sub {{ font-size: 12px; color: #7d879f; margin-top: 2px; }}
  .arch-row .chev {{
    color: #7d879f; font-size: 22px; opacity: 0.6;
    transition: transform 0.18s ease, color 0.18s ease;
  }}
  a.arch-row:hover .chev {{ color: #ffb86b; transform: translateX(2px); opacity: 1; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">Daily Digest · Archive</div>
  <h1>📚 往期归档</h1>
  <div class="sub-top">共 {len(dates)} 期</div>
  <a class="back" href="./">← 回到今日</a>
  <div class="list">
    {"".join(entries)}
  </div>
</div>
</body>
</html>
"""
    (DOCS_DIR / "archive.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# 企微推送
# ---------------------------------------------------------------------------

def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def send_template_card(ctx: dict[str, Any], page_url: str) -> bool:
    """
    发送模板卡片（图文展示型），点击整卡或「查看全部」按钮跳转 HTML 详情页。
    相比 news 类型，template_card 带明确的跳转按钮，交互更清晰。
    """
    date: datetime = ctx["date"]
    weekday = "一二三四五六日"[date.weekday()]

    preview_rows: list[dict[str, str]] = []
    # 选一条最热的热搜作为预览（第一个分类的第一条）
    hot = ctx.get("hot") or {}
    first_cat = next(iter(hot.values()), None)
    if first_cat:
        preview_rows.append({
            "keyname": "🔥 热搜",
            "value": _truncate(first_cat[0]["title"], 22),
        })
    media = ctx.get("media") or {}
    movies = media.get("movies") or []
    musics = media.get("musics") or []
    if movies:
        preview_rows.append({
            "keyname": "🎬 影音",
            "value": _truncate(f"《{movies[0]['title']}》 {movies[0]['subtitle']}", 22),
        })
    elif musics:
        preview_rows.append({
            "keyname": "🎵 音乐",
            "value": _truncate(f"{musics[0]['title']} - {musics[0]['subtitle']}", 22),
        })
    if ctx.get("travels"):
        preview_rows.append({
            "keyname": "🧳 旅游",
            "value": _truncate(ctx["travels"][0]["name"], 22),
        })

    quote_text = ""
    if ctx.get("jokes"):
        quote_text = _truncate(ctx["jokes"][0], 80)

    payload = {
        "msgtype": "template_card",
        "template_card": {
            "card_type": "text_notice",
            "source": {
                "desc": "每日精选 · Daily Digest",
                "desc_color": 0,
            },
            "main_title": {
                "title": f"📬 今日精选·{date:%m 月 %d 日} 星期{weekday}",
                "desc": "热搜 / 冷笑话 / 影音 / 演唱会 / 旅游",
            },
            "horizontal_content_list": preview_rows,
            "jump_list": [{
                "type": 1,
                "url": page_url,
                "title": "🔗 查看完整详情",
            }],
            "card_action": {
                "type": 1,
                "url": page_url,
            },
        },
    }
    if quote_text:
        payload["template_card"]["quote_area"] = {
            "type": 0,
            "title": "😄 今日份冷笑话",
            "quote_text": quote_text,
        }

    try:
        resp = http_post_json(WEBHOOK_URL, payload)
    except Exception as exc:
        log.error("Webhook 请求失败: %s", exc)
        return False

    if resp.get("errcode") == 0:
        log.info("✅ 推送成功（模板卡片 → %s）", page_url)
        return True
    log.error("❌ 推送失败: %s", resp)
    return False


# 保留旧函数名作为别名（兼容）
send_news_card = send_template_card


def send_markdown_fallback(ctx: dict[str, Any]) -> bool:
    """未配置 PAGES_URL 时的降级方案——继续发 markdown。"""
    date: datetime = ctx["date"]
    weekday = "一二三四五六日"[date.weekday()]
    lines = [f"# 📬 每日精选·{date:%Y-%m-%d} 星期{weekday}\n"]

    lines.append("\n## 🔥 今日热搜")
    count = 0
    for cat, items in (ctx.get("hot") or {}).items():
        lines.append(f"\n**{cat}**")
        for m in items[:3]:
            lines.append(f"- {m['title']}  `{m['source']}`")
            count += 1
            if count >= 15:
                break
        if count >= 15:
            break

    lines.append("\n## 😄 冷笑话")
    for j in ctx.get("jokes", [])[:3]:
        lines.append(f"- {j}")

    lines.append("\n## 🎬 影音")
    media = ctx.get("media") or {}
    for m in (media.get("movies") or [])[:2]:
        lines.append(f"- 《{m['title']}》· {m['subtitle']}")
    for m in (media.get("musics") or [])[:2]:
        lines.append(f"- 🎵 {m['title']} - {m['subtitle']}")

    lines.append("\n## 🎤 演唱会关注")
    for c in ctx.get("concerts", []):
        lines.append(f"- {c['artist']}（{c['tag']}）")

    lines.append("\n## 🧳 旅游推荐（深圳出发）")
    for t in ctx.get("travels", []):
        lines.append(f"- **{t['name']}**｜{t.get('season', '')}")

    lines.append("\n> <font color=\"comment\">云端部署后会收到精美 HTML 页面链接 ✨</font>")

    try:
        resp = http_post_json(
            WEBHOOK_URL,
            {"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}},
        )
    except Exception as exc:
        log.error("Webhook 请求失败: %s", exc)
        return False
    return resp.get("errcode") == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log.info("=" * 50)
    log.info("MODE=%s | PAGES_URL=%s", MODE, PAGES_URL or "(未设置)")

    ctx: dict[str, Any] = {
        "date": datetime.now(),
        "hot": collect_hot_by_category(),
        "jokes": collect_jokes(10),
        "media": collect_media(),
        "concerts": collect_concerts(5),
        "travels": collect_travel(3),
        "news": get_daily_news(),
    }

    if MODE in ("html", "all"):
        html = render_html(ctx)
        write_html_files(html, ctx["date"])

    if MODE in ("push", "all"):
        if PAGES_URL:
            page_url = f"{PAGES_URL}/{ctx['date']:%Y-%m-%d}.html"
            ok = send_news_card(ctx, page_url)
        else:
            log.warning("未设置 PAGES_URL，改用 markdown 推送作为降级方案")
            ok = send_markdown_fallback(ctx)
        if not ok:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
