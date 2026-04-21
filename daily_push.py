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
    "虐", "凶", "命案", "遗骸", "战", "袭", "伤", "事故", "灾",
    "抗议", "制裁", "关税", "病", "疫", "癌", "逝世", "自杀",
)


def _is_fun(title: str) -> bool:
    return bool(title) and not any(k in title for k in SERIOUS_KEYWORDS)


def collect_memes(limit: int = 3) -> list[dict[str, str]]:
    """返回结构化热梗：{title, source, link}。"""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    sources = [
        ("/weibo", "微博热搜"),
        ("/douyin", "抖音热搜"),
        ("/zhihu", "知乎热榜"),
        ("/bili", "B 站热搜"),
    ]
    for path, label in sources:
        data = http_get_json(path)
        if not isinstance(data, list):
            continue
        for item in data:
            title = (item.get("title") or "").strip()
            if not title or title in seen or not _is_fun(title):
                continue
            seen.add(title)
            out.append({
                "title": title,
                "source": label,
                "link": item.get("link") or "",
            })

    random.shuffle(out)
    return out[:limit] or [{"title": "今日热梗暂未抓取到，休息一天 🌿", "source": "", "link": ""}]


def collect_jokes(limit: int = 2) -> list[str]:
    jokes: list[str] = []
    seen: set[str] = set()
    for _ in range(limit * 4):
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
    ]
    while len(jokes) < limit:
        pick = random.choice(fallback)
        if pick not in seen:
            seen.add(pick)
            jokes.append(pick)
    return jokes[:limit]


def collect_movies(limit: int = 2) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    maoyan = http_get_json("/maoyan/realtime/movie")
    if isinstance(maoyan, dict):
        for m in (maoyan.get("list") or [])[:3]:
            name = (m.get("movie_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            mid = m.get("movie_id") or ""
            out.append({
                "title": name,
                "subtitle": m.get("release_info") or "",
                "meta": f"累计票房 {m.get('sum_box_desc') or m.get('box_office_desc', '-')}",
                "source": "猫眼实时榜",
                "cover": "",
                "link": f"https://maoyan.com/films/{mid}" if mid else
                        f"https://www.douban.com/search?q={urllib.parse.quote(name)}",
            })
            break

    douban = http_get_json("/douban/weekly/movie")
    if isinstance(douban, list):
        for d in douban[:5]:
            name = (d.get("title") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            subtitle = (d.get("card_subtitle") or "").split("/")
            meta = " / ".join(s.strip() for s in subtitle[2:4]) if len(subtitle) >= 4 else ""
            out.append({
                "title": name,
                "subtitle": f"豆瓣 {d.get('rating', '-')}",
                "meta": meta,
                "source": "豆瓣每周榜",
                "cover": d.get("cover_proxy") or d.get("cover") or "",
                "link": d.get("url") or f"https://www.douban.com/search?q={urllib.parse.quote(name)}",
            })
            if len(out) >= limit:
                break

    return out[:limit] or [{"title": "今日电影榜未抓取到", "subtitle": "", "meta": "", "source": "", "cover": "", "link": ""}]


def get_daily_cover() -> tuple[str, list[str]]:
    """返回 (封面图 URL, 今日 60 秒新闻列表)。"""
    data = http_get_json("/60s") or {}
    return (data.get("image") or FALLBACK_COVER, list(data.get("news") or []))


# ---------------------------------------------------------------------------
# 季节性精选
# ---------------------------------------------------------------------------

CONCERTS_BY_MONTH: dict[int, list[str]] = {
    1: ["薛之谦「天外来物」巡演·多城巡演中", "林俊杰「JJ20 FINAL LAP」巡演"],
    2: ["周深「9 拍」巡回演唱会", "陈奕迅「Fear and Dreams」巡演"],
    3: ["张学友「60+ 巡回演唱会」", "五月天「回到那一天」25 周年巡演"],
    4: ["周杰伦「嘉年华」世界巡演", "华晨宇「火星」演唱会", "邓紫棋「启示录 II」巡演"],
    5: ["林俊杰「JJ20 FINAL LAP」收官场", "刀郎「山歌响起的地方」巡演"],
    6: ["薛之谦「天外来物」收官巡演", "毛不易「小王与小伙伴们」巡演"],
    7: ["张韶涵「旅行的意义」夏日巡演", "任贤齐「齐迹」演唱会"],
    8: ["李荣浩「纵横四海」世界巡演", "伍佰 & China Blue 夏日狂欢"],
    9: ["陶喆「Soul Power II」世界巡演", "五月天大型跨年筹备预热场"],
    10: ["王心凌「CYNDIloves2sing」巡演", "许嵩「寻宝游戏」巡演"],
    11: ["TFBOYS 十三周年演唱会预热", "孙燕姿「就在日落以后」巡演"],
    12: ["跨年演唱会·湖南/江苏/东方/浙江卫视四台", "张杰「曜·北斗」巡演"],
}

TRAVEL_BY_MONTH: dict[int, list[str]] = {
    1: [
        "哈尔滨冰雪大世界·中央大街 + 圣索菲亚教堂夜景",
        "长白山天池雪景·滑雪 + 温泉组合",
    ],
    2: [
        "厦门鼓浪屿·春节南下避寒，海岛漫步 + 闽南小吃",
        "云南元阳梯田·日出云海，冬末春初最佳观赏期",
    ],
    3: [
        "婺源油菜花·全国最经典花海，3 月下旬盛花期",
        "武汉东湖樱花·与日本一较高下的国内赏樱胜地",
    ],
    4: [
        "洛阳牡丹花会·国色天香，谷雨前后最盛",
        "贵州万峰林 + 马岭河峡谷·春日喀斯特地貌云海",
        "新疆伊犁杏花沟·4 月中下旬粉色花海",
        "云南罗平油菜花尾声 + 九龙瀑布",
    ],
    5: [
        "青海茶卡盐湖·5 月起天空之镜开放，人少景美",
        "川西稻城亚丁·五一前后草甸返青，雪山清晰",
        "伊犁薰衣草预热 + 那拉提空中草原",
    ],
    6: [
        "呼伦贝尔大草原·6 月草原返青，骑马 + 星空房",
        "青海湖环湖·油菜花开始绽放，环湖骑行",
        "桂林阳朔·漓江竹筏 + 遇龙河皮划艇",
    ],
    7: [
        "新疆伊犁薰衣草 + 喀拉峻草原·盛夏限定",
        "青海湖油菜花盛花期 + 茶卡星空",
        "内蒙古呼伦贝尔 + 室韦·避暑首选",
    ],
    8: [
        "川西色达 + 稻城亚丁·盛夏高原雪山草原",
        "新疆喀纳斯湖 + 禾木·童话秋初",
        "甘南若尔盖 + 郎木寺·高原避暑秘境",
    ],
    9: [
        "新疆喀纳斯 + 禾木·金秋第一缕秋色",
        "西藏林芝 + 然乌湖·秋日转山转水",
        "青甘大环线·最后一波好天气",
    ],
    10: [
        "新疆北疆大环线·喀纳斯/禾木/白哈巴金秋",
        "内蒙古阿尔山·国内最美秋色之一",
        "川西稻城亚丁 + 米亚罗红叶",
        "额济纳胡杨林·10 月中下旬金色限定",
    ],
    11: [
        "黄山冬韵·云海雾凇 + 温泉",
        "云南腾冲银杏村·11 月中下旬限定金黄",
        "重庆武隆仙女山 + 天生三桥·初冬云雾",
    ],
    12: [
        "哈尔滨·冰雪大世界开园，跨年首选",
        "吉林雾凇岛·长白山温泉 + 雪乡民俗",
        "三亚 / 厦门·南下过冬，海岛温暖",
    ],
}


def _concert_keyword(title: str) -> str:
    """从演唱会文案中提取主要关键词（艺人名 + 巡演名）用于搜索。"""
    if "「" in title and "」" in title:
        artist = title.split("「", 1)[0]
        tour = title.split("「", 1)[1].split("」", 1)[0]
        return f"{artist} {tour}"
    return title.split("·", 1)[0]


def _travel_keyword(title: str) -> str:
    """从旅游推荐中提取地名作为搜索关键词。"""
    return title.split("·", 1)[0].strip()


def collect_concerts(limit: int = 1) -> list[dict[str, str]]:
    pool = CONCERTS_BY_MONTH.get(datetime.now().month, [])
    picks = random.sample(pool, k=min(limit, len(pool))) if pool else ["本月演唱会清单待更新"]
    return [
        {
            "title": t,
            "link": f"https://search.damai.cn/search.html?keyword={urllib.parse.quote(_concert_keyword(t))}",
        }
        for t in picks
    ]


def collect_travel(limit: int = 2) -> list[dict[str, str]]:
    pool = TRAVEL_BY_MONTH.get(datetime.now().month, [])
    picks = random.sample(pool, k=min(limit, len(pool))) if pool else ["本月旅游推荐待更新"]
    return [
        {
            "title": t,
            "link": f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(_travel_keyword(t))}&source=web_search_result_notes",
        }
        for t in picks
    ]


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

    # ---- 热梗：每条可点击跳转到对应平台热搜原帖 ----
    meme_rows = []
    for i, m in enumerate(ctx["memes"], 1):
        inner = (
            f'<span class="rank">{i:02d}</span>'
            '<div class="main">'
            f'<div class="title">{e(m["title"])}</div>'
            f'<div class="sub">{e(m["source"])}</div>'
            '</div>'
        )
        meme_rows.append(_link_or_span(m.get("link", ""), inner, "meme"))
    meme_items = "\n".join(meme_rows)

    # ---- 冷笑话：不需要跳转 ----
    joke_items = "\n".join(f'<div class="joke">{e(j)}</div>' for j in ctx["jokes"])

    # ---- 电影：跳转到豆瓣/猫眼详情 ----
    movie_rows = []
    for m in ctx["movies"]:
        poster = (
            f'<img src="{e(m["cover"])}" alt="" class="poster" loading="lazy">'
            if m.get("cover") else '<div class="poster poster-empty">🎬</div>'
        )
        meta = f'<div class="meta">{e(m["meta"])}</div>' if m.get("meta") else ""
        inner = (
            f'{poster}'
            '<div class="main">'
            f'<div class="title">{e(m["title"])}</div>'
            f'<div class="sub"><span class="accent">{e(m["subtitle"])}</span></div>'
            f'{meta}'
            f'<div class="tag">{e(m["source"])}</div>'
            '</div>'
        )
        movie_rows.append(_link_or_span(m.get("link", ""), inner, "movie"))
    movie_items = "\n".join(movie_rows)

    # ---- 演唱会：跳大麦网搜索 ----
    concert_rows = []
    for c in ctx["concerts"]:
        inner = (
            '<span class="dot concert-dot"></span>'
            f'<div class="main"><div class="title">{e(c["title"])}</div>'
            '<div class="sub">大麦网搜索 · 查看场次与票价</div></div>'
        )
        concert_rows.append(_link_or_span(c.get("link", ""), inner, "concert"))
    concert_items = "\n".join(concert_rows)

    # ---- 旅游：跳小红书搜索 ----
    travel_rows = []
    for t in ctx["travels"]:
        inner = (
            '<span class="dot travel-dot"></span>'
            f'<div class="main"><div class="title">{e(t["title"])}</div>'
            '<div class="sub">小红书搜索 · 查看攻略与游记</div></div>'
        )
        travel_rows.append(_link_or_span(t.get("link", ""), inner, "travel"))
    travel_items = "\n".join(travel_rows)

    # ---- 60 秒读世界 ----
    news_items = "\n".join(f'<li>{e(n)}</li>' for n in (ctx["news"] or [])[:8])
    news_block = f"""
  <section class="news-section">
    <div class="sec-head">
      <h2>60 秒读懂世界</h2>
      <div class="count">{min(len(ctx["news"] or []), 8)} 条</div>
    </div>
    <ul class="news-list">{news_items}</ul>
  </section>""" if news_items else ""

    cover = e(ctx["cover"])
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
  .cover {{
    margin-top: 18px;
    border-radius: 14px;
    overflow: hidden;
    aspect-ratio: 1068/455;
    background: var(--bg-soft) center/cover no-repeat url('{cover}');
    box-shadow: 0 14px 40px -16px rgba(0,0,0,0.6);
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
  }}
  .concert-dot {{ background: var(--sky); box-shadow: 0 0 10px rgba(130,177,255,0.5); }}
  .travel-dot  {{ background: var(--mint); box-shadow: 0 0 10px rgba(109,218,168,0.5); }}

  /* ========== 60 秒 ========== */
  .news-section {{ margin-top: 22px; }}
  .news-list {{
    list-style: none;
    margin: 0; padding: 8px 18px 14px;
  }}
  .news-list li {{
    position: relative;
    padding: 6px 0 6px 16px;
    color: var(--fg-2);
    font-size: 13px;
    line-height: 1.75;
  }}
  .news-list li::before {{
    content: '';
    position: absolute;
    left: 0; top: 14px;
    width: 6px; height: 6px;
    background: var(--fg-3);
    border-radius: 50%;
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
    <h1>今日热梗·生活资讯</h1>
    <div class="date">{e(date_str)}</div>
    <div class="cover"></div>
  </header>

  <section>
    <div class="sec-head">
      <h2>🔥 今日热梗</h2>
      <div class="count">{len(ctx["memes"])} 条 · 点击查看原帖</div>
    </div>
    {meme_items}
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
      <h2>🎬 电影榜单</h2>
      <div class="count">{len(ctx["movies"])} 部 · 点击看详情</div>
    </div>
    {movie_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>🎤 本月演唱会</h2>
      <div class="count">{len(ctx["concerts"])} 场</div>
    </div>
    {concert_items}
  </section>

  <section>
    <div class="sec-head">
      <h2>🧳 本季旅游目的地</h2>
      <div class="count">{len(ctx["travels"])} 处</div>
    </div>
    {travel_items}
  </section>

  {news_block}

  <footer>
    <div class="sources">微博 · 抖音 · 知乎 · B 站 · 猫眼 · 豆瓣 · 60s</div>
    <div>生成于 {e(generated)} · <a href="./">往期归档</a></div>
  </footer>
</div>
</body>
</html>
"""


def write_html_files(html: str, date: datetime) -> Path:
    """写入 docs/index.html 以及归档 docs/YYYY-MM-DD.html。返回 index 路径。"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    archive = DOCS_DIR / f"{date:%Y-%m-%d}.html"
    index = DOCS_DIR / "index.html"
    archive.write_text(html, encoding="utf-8")
    index.write_text(html, encoding="utf-8")
    log.info("HTML 已生成: %s", archive.name)
    return index


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

    # 取头三条作为卡片内预览列表
    preview_rows: list[dict[str, str]] = []
    for m in ctx["memes"][:2]:
        preview_rows.append({
            "keyname": "🔥 热梗",
            "value": _truncate(m["title"], 20),
        })
    if ctx["movies"]:
        mv = ctx["movies"][0]
        preview_rows.append({
            "keyname": "🎬 电影",
            "value": _truncate(f"《{mv['title']}》 {mv['subtitle']}", 20),
        })
    if ctx["travels"]:
        preview_rows.append({
            "keyname": "🧳 旅游",
            "value": _truncate(ctx["travels"][0]["title"], 20),
        })

    quote_text = ""
    if ctx["jokes"]:
        quote_text = _truncate(ctx["jokes"][0], 80)

    payload = {
        "msgtype": "template_card",
        "template_card": {
            "card_type": "news_notice",
            "source": {
                "desc": "每日精选 · Daily Digest",
                "desc_color": 0,
            },
            "main_title": {
                "title": f"📬 今日热梗·{date:%m 月 %d 日} 星期{weekday}",
                "desc": "为你精选 10 条热梗 / 笑话 / 电影 / 旅游",
            },
            "card_image": {
                "url": ctx["cover"],
                "aspect_ratio": 2.25,
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
    lines = [f"# 📬 每日热梗·{date:%Y-%m-%d} 星期{weekday}\n"]

    lines.append("\n## 🔥 今日热梗")
    for i, m in enumerate(ctx["memes"], 1):
        lines.append(f"**{i}.** {m['title']}  `{m['source']}`")

    lines.append("\n## 😄 冷笑话")
    for j in ctx["jokes"]:
        lines.append(f"- {j}")

    lines.append("\n## 🎬 电影")
    for m in ctx["movies"]:
        lines.append(f"- 《{m['title']}》· {m['subtitle']}｜{m['meta']}")

    lines.append("\n## 🎤 演唱会")
    for c in ctx["concerts"]:
        lines.append(f"- {c['title']}")

    lines.append("\n## 🧳 旅游推荐")
    for t in ctx["travels"]:
        lines.append(f"- {t['title']}")

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

    cover, news = get_daily_cover()
    ctx: dict[str, Any] = {
        "date": datetime.now(),
        "cover": cover,
        "news": news,
        "memes": collect_memes(3),
        "jokes": collect_jokes(2),
        "movies": collect_movies(2),
        "concerts": collect_concerts(1),
        "travels": collect_travel(2),
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
