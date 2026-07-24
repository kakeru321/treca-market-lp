#!/usr/bin/env python3
"""build_site.py — treca_draft_*.json から静的LPを生成する

入力: ~/Documents/treca/treca_draft_YYYYMMDD.json (daily-treca-news が生成)
出力: docs/ (GitHub Pages 公開ディレクトリ)
  - index.html          今日のTOP3 + アーカイブリンク + CTA
  - daily/YYYYMMDD.html 日別アーカイブページ (SEOロングテール)
  - about.html / privacy.html は静的 (このスクリプトでは触らない)

使い方:
  python3 generator/build_site.py            # 直近30日分を生成
  python3 generator/build_site.py --days 60
  python3 generator/build_site.py --push     # 生成 + git commit/push (launchd 日次用)
                                             # 失敗時は DISCORD_WEBHOOK_AUTOMATION に通知
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# settings.local.json を env に補完（DISCORD_WEBHOOK_AUTOMATION 用）
_SETTINGS = os.path.expanduser("~/.claude/settings.local.json")
if os.path.exists(_SETTINGS):
    with open(_SETTINGS, encoding="utf-8") as _f:
        for _k, _v in json.load(_f).get("env", {}).items():
            if _k not in os.environ:
                os.environ[_k] = _v

DRAFT_DIR = Path.home() / "Documents" / "treca"
SITE_DIR = Path(__file__).resolve().parent.parent / "docs"
SITE_TITLE = "トレカ相場ログ｜トト"
SITE_URL = "https://kakeru321.github.io/treca-market-lp"
X_URL = "https://x.com/tcg_marketP"
WEEKDAYS = "月火水木金土日"

# アフィリエイトCTA。提携承認後に url を差し替える (None = 準備中表示)
CTA_SELL_URL = None  # トレトク等 買取査定
CTA_BUY_URL = None   # 楽天市場 (もしも経由)

PR_NOTICE = "本サイトはアフィリエイト広告（準備中を含む）を利用しています。"

CSS = """
:root { --bg:#0f1218; --card:#1a1f2b; --text:#e8eaf0; --sub:#9aa3b5;
        --up:#ff5c5c; --down:#4da3ff; --accent:#f5c542; --line:#2a3040; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text);
       font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
       line-height:1.7; }
.wrap { max-width:640px; margin:0 auto; padding:16px; }
.pr { font-size:11px; color:var(--sub); text-align:center; padding:6px 0; }
header.site h1 { font-size:20px; }
header.site .tagline { color:var(--sub); font-size:13px; margin-bottom:8px; }
.date-label { color:var(--accent); font-size:14px; font-weight:600; margin:16px 0 8px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:14px; margin-bottom:12px; display:flex; gap:12px; }
.card img { width:72px; height:auto; object-fit:contain; align-self:flex-start;
            border-radius:6px; background:#fff; }
.card .body { flex:1; min-width:0; }
.card .name { font-weight:700; font-size:15px; }
.card .kind { display:inline-block; font-size:11px; color:var(--bg);
              background:var(--accent); border-radius:4px; padding:0 6px; margin-left:6px; }
.card .price { font-size:14px; margin:4px 0; }
.card .pct { font-weight:700; }
.pct.up { color:var(--up); } .pct.down { color:var(--down); }
.card .comment { font-size:13px; color:var(--sub); }
.cta { display:flex; gap:10px; margin:20px 0; }
.cta a, .cta span { flex:1; text-align:center; padding:12px 8px; border-radius:10px;
        font-size:14px; font-weight:700; text-decoration:none; }
.cta .sell { background:var(--accent); color:#1a1a1a; }
.cta .buy { background:#bf0000; color:#fff; }
.cta .pending { background:var(--line); color:var(--sub); font-weight:400; }
.archive { margin:24px 0; }
.archive h2 { font-size:16px; margin-bottom:8px; }
.archive a { display:block; color:var(--text); text-decoration:none; font-size:14px;
             padding:8px 4px; border-bottom:1px solid var(--line); }
.archive a:hover { color:var(--accent); }
.archive .sum { color:var(--sub); font-size:12px; }
footer { color:var(--sub); font-size:12px; text-align:center; padding:24px 0; }
footer a { color:var(--sub); }
.follow { display:block; text-align:center; background:var(--card); border:1px solid var(--line);
          border-radius:10px; padding:12px; margin:16px 0; color:var(--text);
          text-decoration:none; font-size:14px; }
.follow b { color:var(--accent); }
"""


def load_drafts(days: int):
    """直近days日分のdraftを新しい順で返す (video.cardsを持つもののみ)"""
    files = sorted(DRAFT_DIR.glob("treca_draft_*.json"), reverse=True)
    out = []
    for f in files:
        m = re.match(r"treca_draft_(\d{8})\.json", f.name)
        if not m:
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        video = d.get("video") or {}
        cards = video.get("cards") or []
        if not cards:
            continue
        out.append({"date": m.group(1), "cards": cards,
                    "date_label": video.get("date_label") or fmt_date(m.group(1))})
        if len(out) >= days:
            break
    return out


def fmt_date(yyyymmdd: str) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d")
    return f"{dt.month}月{dt.day}日({WEEKDAYS[dt.weekday()]})"


def esc(s) -> str:
    return html.escape(str(s or ""))


def card_html(c: dict) -> str:
    pct = c.get("change_pct") or 0
    cls = "up" if pct >= 0 else "down"
    sign = "+" if pct >= 0 else ""
    img = f'<img src="{esc(c.get("image_url"))}" alt="{esc(c.get("name"))}" loading="lazy">' \
        if c.get("image_url") else ""
    return f"""<div class="card">{img}<div class="body">
<div class="name">{esc(c.get('name'))}<span class="kind">{esc(c.get('kind'))}</span></div>
<div class="price">¥{c.get('price_prev', 0):,} → ¥{c.get('price_now', 0):,}
 <span class="pct {cls}">({sign}{pct}%)</span></div>
<div class="comment">{esc(c.get('comment'))}</div>
</div></div>"""


def cta_html() -> str:
    sell = (f'<a class="sell" href="{CTA_SELL_URL}" rel="sponsored noopener">売るなら 高価買取査定 ▶</a>'
            if CTA_SELL_URL else '<span class="pending">買取査定リンク準備中</span>')
    buy = (f'<a class="buy" href="{CTA_BUY_URL}" rel="sponsored noopener">買うなら 楽天で探す ▶</a>'
           if CTA_BUY_URL else '<span class="pending">購入リンク準備中</span>')
    return f'<div class="cta">{sell}{buy}</div>'


def page(title: str, desc: str, body: str, path_depth: int = 0) -> str:
    root = "../" * path_depth
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<style>{CSS}</style>
</head>
<body>
<div class="pr">{PR_NOTICE}</div>
<div class="wrap">
<header class="site">
<h1><a href="{root}index.html" style="color:inherit;text-decoration:none">{SITE_TITLE}</a></h1>
<div class="tagline">スニダン実売データで毎朝更新。高騰・下落をトトの相場観つきで。</div>
</header>
{body}
<footer>
データ出典: スニーカーダンク実売価格の日次集計（当サイト調べ）<br>
<a href="{root}about.html">運営者情報</a> ・ <a href="{root}privacy.html">プライバシーポリシー</a><br>
&copy; 2026 トレカ相場ログ
</footer>
</div>
</body>
</html>"""


def daily_summary(cards) -> str:
    """アーカイブ一覧用の1行サマリ"""
    parts = []
    for c in cards[:3]:
        pct = c.get("change_pct") or 0
        sign = "+" if pct >= 0 else ""
        name = re.sub(r"\s+\S+/\S+$", "", str(c.get("name") or ""))  # 型番除去で短縮
        parts.append(f"{name} {sign}{pct}%")
    return " / ".join(parts)


def build(days: int):
    drafts = load_drafts(days)
    if not drafts:
        raise SystemExit("no drafts found")

    daily_dir = SITE_DIR / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    # 日別アーカイブページ
    for d in drafts:
        cards_h = "\n".join(card_html(c) for c in d["cards"])
        names = "、".join(str(c.get("name")) for c in d["cards"])
        body = f"""<div class="date-label">{esc(d['date_label'])} の値動きTOP3</div>
{cards_h}
{cta_html()}
<a class="follow" href="{X_URL}">毎朝の速報はXで ▶ <b>@tcg_marketP</b></a>
<div class="archive"><h2>他の日を見る</h2><a href="../index.html">最新の相場を見る ▶</a></div>"""
        title = f"{d['date_label']}のトレカ相場｜{names[:40]}"
        desc = f"{d['date_label']}のポケカ・トレカ価格変動TOP3。{daily_summary(d['cards'])}。スニダン実売データで毎朝更新。"
        (daily_dir / f"{d['date']}.html").write_text(
            page(title, desc, body, path_depth=1), encoding="utf-8")

    # index (最新日 + アーカイブ一覧)
    latest = drafts[0]
    cards_h = "\n".join(card_html(c) for c in latest["cards"])
    archive_h = "\n".join(
        f'<a href="daily/{d["date"]}.html">{esc(d["date_label"])}'
        f'<span class="sum"> — {esc(daily_summary(d["cards"]))}</span></a>'
        for d in drafts[1:])
    body = f"""<div class="date-label">{esc(latest['date_label'])} の値動きTOP3</div>
{cards_h}
{cta_html()}
<a class="follow" href="{X_URL}">毎朝の速報はXで ▶ <b>@tcg_marketP</b></a>
<div class="archive"><h2>過去の相場アーカイブ</h2>{archive_h}</div>"""
    desc = (f"ポケカ・トレカの高騰/下落を毎朝更新。{latest['date_label']}は"
            f"{daily_summary(latest['cards'])}。スニダン実売データ×トトの相場観。")
    (SITE_DIR / "index.html").write_text(
        page(SITE_TITLE, desc, body), encoding="utf-8")

    print(f"built: index + {len(drafts)} daily pages -> {SITE_DIR}")


def notify_automation(msg: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_AUTOMATION", "")
    if not url:
        return
    try:
        data = json.dumps({"content": msg}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "DiscordBot (https://github.com, 1.0)")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def git_push():
    """docs/ の変更を commit + push。変更が無ければ何もしない"""
    repo = SITE_DIR.parent
    run = lambda *a: subprocess.run(
        ["git", *a], cwd=repo, check=True, capture_output=True, text=True)
    run("add", "docs")
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if diff.returncode == 0:
        print("no changes; skip push")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    run("commit", "-m", f"chore: daily site update {today}")
    run("push", "origin", "main")
    print("pushed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--push", action="store_true",
                    help="生成後に git commit + push（launchd 日次実行用）")
    args = ap.parse_args()
    try:
        build(args.days)
        if args.push:
            git_push()
    except Exception as e:
        notify_automation(f"⚠️ treca-market-lp 日次更新失敗: {type(e).__name__}: {e}")
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
