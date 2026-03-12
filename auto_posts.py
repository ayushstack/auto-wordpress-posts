"""
auto_posts.py — Fully Automatic WordPress Post Creator (v12)
============================================================
Changes from v11:
  ✅ No featured image (removed)
  ✅ Telegram bot notifications with full run summary
  ✅ GitHub Actions ready (cron at 10:00 AM IST = 04:30 UTC)

Setup:
  1. Fill in WP credentials below
  2. Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
  3. Place service_account.json in same folder as this script
  4. Run: python auto_posts.py --dry-run

Usage:
  python auto_posts.py                  # runs with default settings
  python auto_posts.py --posts 5        # create 5 posts
  python auto_posts.py --dry-run        # preview without posting

GitHub Actions Cron (10:00 AM IST = 04:30 UTC):
  See .github/workflows/auto_posts.yml
"""

import requests
import random
import re
import time
import argparse
import os
from datetime import datetime


# ============================================================
# CONFIGURATION — Fill these in before running
# ============================================================

WP_URL       = "https://unityimage.com/wp-json/wp/v2"
USERNAME           = os.environ.get("WP_USERNAME", "your_wp_username")
APP_PASSWORD       = os.environ.get("WP_APP_PASSWORD", "your_app_password")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "your_token")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "your_chat_id")

# --- Post settings ---
POSTS_PER_RUN      = 1
IMAGES_PER_HEADING = 10    # 5 headings x 10 = 50 images per post
POST_STATUS        = "publish"  # "draft" or "publish"

# --- Google Indexing ---
SERVICE_ACCOUNT_FILE = "service_account.json"

# --- Fallback category name (must exist in your WordPress) ---
FALLBACK_CATEGORY  = "Trending"

# --- Tracking files ---
USED_KEYWORDS_FILE = "used_keywords.txt"
LOG_FILE           = "logs/auto_posts.log"

AUTH = (USERNAME, APP_PASSWORD)


# ============================================================
# SEED KEYWORDS — Your niche topics
# ============================================================

SEED_KEYWORDS = [
    "hidden face girl dp",
    "hidden face girl photo",
    "hidden face girl wallpaper",
    "attitude girl photo",
    "attitude girl wallpaper",
    "attitude girl dp",
    "sad girl dp",
    "sad girl photo",
    "sad girl wallpaper",
    "aesthetic girl dp",
    "aesthetic girl wallpaper",
    "cute girl dp",
    "cute girl photo",
    "instagram girl dp",
    "instagram girl photo",
    "stylish girl dp",
    "stylish girl photo",
    "stylish girl wallpaper",
    "beautiful girl dp",
    "alone girl dp",
    "cool girl dp",
    "romantic girl dp",
    "simple girl dp",
    "black dress girl dp",
    "college girl dp",
    "desi girl dp",
    "royal girl dp",
    "modern girl dp",
    "innocent girl dp",
]


# ============================================================
# TITLE TEMPLATES
# ============================================================

TITLE_TEMPLATES = [
    "100+ {kw} HD Images Free Download",
    "Best 999+ {kw} Photos Collection",
    "Latest {kw} Wallpapers HD Download",
    "Top 100 {kw} Pictures Free",
    "[Best] {kw} HD Images Free",
    "[999+] {kw} Photos HD 2025",
    "[555+] {kw} Wallpapers Free Download",
    "Stunning {kw} Pictures Collection HD",
    "[Download] {kw} HD Images 2026",
    "Latest 555+ {kw} Photos Collection",
    "New {kw} HD Wallpapers Free",
    "Amazing {kw} Images Download Free",
]


# ============================================================
# SUBHEADING FALLBACK SETS
# ============================================================

SUBHEADING_FALLBACK = [
    ["Stylish", "Cute", "Aesthetic", "Attitude", "Sad"],
    ["Beautiful", "Simple", "Cool", "Romantic", "Alone"],
    ["HD", "Instagram", "Whatsapp", "Latest", "New"],
    ["Royal", "HD Photos", "HD Wallpaper", "Stylish", "Unique"],
    ["Black Dress", "College", "Desi", "Innocent", "Mirror Selfie"],
    ["Hidden Face", "Instagram Profile", "Dark", "Vintage", "Classy"],
]


# ============================================================
# INTRO PARAGRAPH TEMPLATES
# ============================================================

INTRO_TEMPLATES = [
    (
        "Are you searching for the best {topic} images to update your profile? "
        "Your search ends right here because we have put together the most beautiful "
        "and trending collection just for you. "
        "Every image in this collection is available in full HD quality and is "
        "completely free to download with just one click. "
        "These stunning photos are perfect for setting as your Instagram or WhatsApp "
        "display picture and will make your profile stand out from the crowd. "
        "Scroll down and explore the full collection below to find your perfect match."
    ),
    (
        "If you are tired of boring profile pictures that look just like everyone else, "
        "this {topic} collection is exactly what you need. "
        "We have brought together hundreds of unique and eye-catching images covering "
        "every style from cute and aesthetic to bold and attitude looks. "
        "All photos are in HD quality and available for free download without any "
        "registration or payment required. "
        "Whether you want to update your Instagram DP, WhatsApp profile picture or "
        "phone wallpaper, you will find the perfect image right here. "
        "Start scrolling and pick the ones you love the most."
    ),
    (
        "Finding the perfect {topic} for your social media profile just got a whole "
        "lot easier with our latest collection. "
        "This gallery features a wide variety of beautiful and trending images that "
        "have been handpicked to give you the best options in one place. "
        "Each and every photo is available in crystal clear HD resolution and you "
        "can download them all completely free of charge. "
        "Set any of these as your Instagram or WhatsApp display picture and instantly "
        "upgrade the look of your profile. "
        "Browse through the full gallery below and download your favourites today."
    ),
    (
        "Stop scrolling because you have just found the best {topic} collection on "
        "the internet right now. "
        "This carefully put together gallery includes some of the most popular and "
        "trending images across every style and mood you could want. "
        "Every single image here is full HD quality and completely free to download "
        "with no hidden charges or sign up needed. "
        "These photos are ideal for your Instagram DP, WhatsApp profile picture or "
        "even as a wallpaper on your phone or laptop. "
        "Take your time going through the collection below and save the ones that "
        "catch your eye."
    ),
]


# ============================================================
# RUN STATS — collects data for Telegram summary
# ============================================================

class RunStats:
    def __init__(self):
        self.start_time    = datetime.now()
        self.posts_created = []   # list of dicts: {title, link, category, keyword}
        self.posts_failed  = []   # list of keywords that failed
        self.indexed       = []   # list of URLs successfully submitted to Google
        self.index_failed  = []   # list of URLs that failed indexing
        self.keywords_used = []   # fresh keywords selected this run
        self.dry_run       = False

    def elapsed(self):
        delta = datetime.now() - self.start_time
        mins  = int(delta.total_seconds() // 60)
        secs  = int(delta.total_seconds() % 60)
        return f"{mins}m {secs}s"


STATS = RunStats()


# ============================================================
# LOGGING
# ============================================================

def log(msg):
    os.makedirs("logs", exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def send_telegram(message):
    """
    Sends a message to your Telegram bot.
    Max message length for Telegram is 4096 chars — auto-truncated.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("  ⚠ Telegram not configured — skipping notification")
        return

    # Telegram max message size
    if len(message) > 4000:
        message = message[:3997] + "..."

    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }

    try:
        r = requests.post(url, data=params, timeout=15)
        if r.status_code == 200:
            log("  ✓ Telegram notification sent")
        else:
            log(f"  ✗ Telegram error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log(f"  ✗ Telegram send error: {e}")


def build_telegram_summary(stats):
    """
    Builds a nicely formatted Telegram message with full run details.
    Uses HTML formatting supported by Telegram.
    """
    run_date = stats.start_time.strftime("%d %b %Y, %I:%M %p IST")
    mode     = "🔍 DRY RUN" if stats.dry_run else "🚀 LIVE RUN"

    lines = [
        f"<b>🤖 Auto Posts Report</b>",
        f"<b>Date:</b> {run_date}",
        f"<b>Mode:</b> {mode}",
        f"<b>Time Taken:</b> {stats.elapsed()}",
        "",
        f"<b>📊 Summary</b>",
        f"✅ Posts Created : <b>{len(stats.posts_created)}</b>",
        f"❌ Posts Failed  : <b>{len(stats.posts_failed)}</b>",
        f"🔍 Indexed (Google): <b>{len(stats.indexed)}</b>",
        f"⚠️ Index Failed  : <b>{len(stats.index_failed)}</b>",
        "",
    ]

    # Created posts detail
    if stats.posts_created:
        lines.append("<b>📝 Posts Created:</b>")
        for i, p in enumerate(stats.posts_created, 1):
            lines.append(
                f"{i}. <b>{p['title']}</b>\n"
                f"   📂 {p['category']} | 🔑 {p['keyword']}\n"
                f"   🔗 <a href=\"{p['link']}\">{p['link']}</a>"
            )
        lines.append("")

    # Failed posts
    if stats.posts_failed:
        lines.append("<b>❌ Failed Keywords:</b>")
        for kw in stats.posts_failed:
            lines.append(f"  • {kw}")
        lines.append("")

    # Google Indexed URLs
    if stats.indexed:
        lines.append("<b>🔍 Google Indexing Requested:</b>")
        for url in stats.indexed:
            lines.append(f"  • {url}")
        lines.append("")

    # Index failures
    if stats.index_failed:
        lines.append("<b>⚠️ Indexing Failed:</b>")
        for url in stats.index_failed:
            lines.append(f"  • {url}")
        lines.append("")

    lines.append("─────────────────────")
    lines.append(f"<i>unityimage.com | Auto Posts v12</i>")

    return "\n".join(lines)


# ============================================================
# USED KEYWORDS
# ============================================================

def load_used_keywords():
    if not os.path.exists(USED_KEYWORDS_FILE):
        return set()
    with open(USED_KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


def save_used_keyword(kw):
    with open(USED_KEYWORDS_FILE, "a", encoding="utf-8") as f:
        f.write(kw.strip().lower() + "\n")


# ============================================================
# GOOGLE AUTOCOMPLETE
# ============================================================

def fetch_autocomplete(seed):
    url     = "https://suggestqueries.google.com/complete/search"
    params  = {"client": "firefox", "q": seed, "hl": "en"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data        = r.json()
            suggestions = data[1] if len(data) > 1 else []
            return [s.strip().lower() for s in suggestions if s.strip()]
    except Exception as e:
        log(f"  Autocomplete error for '{seed}': {e}")
    return []


def collect_keywords(seeds, used_keywords):
    all_kws = []
    for seed in seeds:
        suggestions = fetch_autocomplete(seed)
        log(f"  Seed '{seed}' → {len(suggestions)} suggestions")
        all_kws.extend(suggestions)
        time.sleep(0.5)

    all_kws.extend([s.lower() for s in seeds])

    seen, unique = set(), []
    for kw in all_kws:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    fresh = [kw for kw in unique if kw not in used_keywords and len(kw.split()) >= 3]
    log(f"  Total fresh keywords available: {len(fresh)}")
    return fresh


# ============================================================
# TITLE CASE HELPER
# ============================================================

def title_case_keyword(kw):
    always_upper = {"dp", "hd", "4k"}
    stop_words   = {"a", "an", "the", "and", "or", "for", "of", "in", "on", "at", "to"}
    words  = kw.split()
    result = []
    for i, w in enumerate(words):
        if w in always_upper:
            result.append(w.upper())
        elif i == 0 or w not in stop_words:
            result.append(w.capitalize())
        else:
            result.append(w)
    return " ".join(result)


# ============================================================
# TITLE GENERATOR
# ============================================================

def generate_title(kw):
    template = random.choice(TITLE_TEMPLATES)
    return template.replace("{kw}", title_case_keyword(kw))


# ============================================================
# SUBHEADINGS FROM GOOGLE AUTOCOMPLETE
# ============================================================

def fetch_subheadings_from_google(keyword, count=5):
    log(f"  Fetching subheadings from Google for: '{keyword}'")
    suggestions = fetch_autocomplete(keyword)

    result = []
    for s in suggestions:
        result.append(title_case_keyword(s))
        if len(result) >= count:
            break

    log(f"  Google returned {len(result)} subheading suggestions")

    if len(result) < count:
        modifier_set = random.choice(SUBHEADING_FALLBACK)
        pretty_kw    = title_case_keyword(keyword)
        for mod in modifier_set:
            if len(result) >= count:
                break
            candidate = f"{mod} {pretty_kw}"
            if candidate not in result:
                result.append(candidate)
        log(f"  Fallback added — total subheadings: {len(result)}")

    return result[:count]


# ============================================================
# INTRO PARAGRAPH
# ============================================================

def generate_intro(keyword):
    pretty   = title_case_keyword(keyword)
    template = random.choice(INTRO_TEMPLATES)
    intro    = template.replace("{topic}", pretty)
    log(f"  ✓ Intro generated ({len(intro)} chars)")
    return intro


# ============================================================
# META DESCRIPTION
# ============================================================

def generate_meta_description(intro):
    sentences = re.split(r'(?<=[.?!])\s+', intro.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    meta = ""
    for sentence in sentences:
        if len(meta) + len(sentence) + 1 <= 155:
            meta += sentence + " "
        else:
            break

    return meta.strip()


# ============================================================
# GOOGLE INDEXING API
# ============================================================

def request_google_indexing(post_url):
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        log(f"  ⚠ {SERVICE_ACCOUNT_FILE} not found — skipping indexing request")
        STATS.index_failed.append(post_url)
        return

    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )

        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {credentials.token}"
        }

        body = {"url": post_url, "type": "URL_UPDATED"}

        r = requests.post(
            "https://indexing.googleapis.com/v3/urlNotifications:publish",
            headers=headers,
            json=body,
            timeout=15
        )

        if r.status_code == 200:
            log(f"  ✓ Google indexing requested: {post_url}")
            STATS.indexed.append(post_url)
        else:
            log(f"  ✗ Indexing API error {r.status_code}: {r.text[:120]}")
            STATS.index_failed.append(post_url)

    except ImportError:
        log("  ⚠ google-auth not installed — run: pip install google-auth")
        STATS.index_failed.append(post_url)
    except Exception as e:
        log(f"  ✗ Indexing error: {e}")
        STATS.index_failed.append(post_url)


# ============================================================
# WP CATEGORIES
# ============================================================

def fetch_wp_categories():
    try:
        r = requests.get(
            f"{WP_URL}/categories",
            params={"per_page": 100},
            auth=AUTH,
            timeout=10
        )
        cats = r.json()
        log(f"  Fetched {len(cats)} categories from WordPress:")
        for cat in cats:
            log(f"    ID={cat['id']}  Name='{cat['name']}'")
        return cats
    except Exception as e:
        log(f"  Category fetch error: {e}")
        return []


def match_category(title, categories):
    title_lower = title.lower()

    for cat in categories:
        cat_name = cat["name"].lower()
        if cat_name == FALLBACK_CATEGORY.lower():
            continue
        cat_words   = cat_name.split()
        match_words = cat_words[:3]
        if all(word in title_lower for word in match_words):
            log(f"  ✓ Category matched: '{cat['name']}' (ID={cat['id']})")
            return cat["id"]

    for cat in categories:
        if cat["name"].lower() == FALLBACK_CATEGORY.lower():
            log(f"  No match — fallback to '{FALLBACK_CATEGORY}' (ID={cat['id']})")
            return cat["id"]

    if categories:
        log(f"  '{FALLBACK_CATEGORY}' not found — using first category (ID={categories[0]['id']})")
        return categories[0]["id"]

    log("  WARNING: No categories found — using ID=1")
    return 1


# ============================================================
# WP MEDIA
# ============================================================

_media_cache = None

def fetch_all_wp_media():
    global _media_cache
    if _media_cache is not None:
        return _media_cache

    log("  Fetching WP Media Library (runs once per session)...")
    all_items = []
    page = 1

    while True:
        r = requests.get(
            f"{WP_URL}/media",
            params={"media_type": "image", "per_page": 100, "page": page},
            auth=AUTH,
            timeout=30
        )
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        all_items.extend(data)
        log(f"    Page {page} → {len(data)} images (total: {len(all_items)})")
        page += 1
        time.sleep(0.3)

    log(f"  Total images in library: {len(all_items)}")
    _media_cache = all_items
    return all_items


# ============================================================
# HTML GALLERY BUILDER
# ============================================================

def build_html_gallery(subheadings, all_media, images_per_heading, keyword, intro_text):
    pretty_kw  = title_case_keyword(keyword)
    html_parts = []

    if intro_text:
        html_parts.append(
            f'<p style="font-size:16px;line-height:1.8;margin-bottom:28px;color:#333;">'
            f'{intro_text}'
            f'</p>'
        )

    pool = list(all_media)
    random.shuffle(pool)

    needed = images_per_heading * len(subheadings)

    while len(pool) < needed:
        extra = list(all_media)
        random.shuffle(extra)
        pool.extend(extra)

    cursor = 0
    for sub in subheadings:
        chunk   = pool[cursor: cursor + images_per_heading]
        cursor += images_per_heading

        html_parts.append(f'<h2>{sub}</h2>')

        for item in chunk:
            url = item.get("source_url", "")
            alt = item.get("alt_text") or pretty_kw

            html_parts.append(
                f'<figure style="margin-bottom:20px;text-align:center;">'
                f'<img src="{url}" alt="{alt}" style="width:100%;border-radius:8px;" />'
                f'<div style="margin-top:6px;color:#555;font-size:13px;">{alt}</div>'
                f'</figure>'
            )

    return "\n".join(html_parts)


# ============================================================
# CREATE WORDPRESS POST — NO featured image
# ============================================================

def create_wp_post(title, content, category_id, focus_kw, meta_desc):
    """
    Creates a WordPress post WITHOUT a featured image.
    featured_media is intentionally omitted.
    """
    data = {
        "title":      title,
        "content":    content,
        "status":     POST_STATUS,
        "categories": [category_id],
        "meta": {
            "_yoast_wpseo_focuskw":  focus_kw,
            "_yoast_wpseo_metadesc": meta_desc,
        }
    }
    try:
        r      = requests.post(f"{WP_URL}/posts", json=data, auth=AUTH, timeout=30)
        result = r.json()
        return result.get("id"), result.get("link", "")
    except Exception as e:
        log(f"  WP post creation error: {e}")
        return None, ""


# ============================================================
# MAIN PIPELINE
# ============================================================

def run(posts_to_create=POSTS_PER_RUN, dry_run=False):
    STATS.dry_run = dry_run

    log("=" * 60)
    log(f"Auto Posts v12 | target={posts_to_create} posts | dry_run={dry_run}")
    log("=" * 60)

    # Send start notification to Telegram
    send_telegram(
        f"🚀 <b>Auto Posts Started</b>\n"
        f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n"
        f"Target: {posts_to_create} post(s)\n"
        f"Time: {STATS.start_time.strftime('%d %b %Y, %I:%M %p')}"
    )

    used_keywords = load_used_keywords()
    log(f"Loaded {len(used_keywords)} already-used keywords")

    log("Fetching WordPress categories...")
    categories = fetch_wp_categories() if not dry_run else [
        {"id": 1,  "name": "Hidden Face Girl Pic"},
        {"id": 2,  "name": "Sad Girl DP"},
        {"id": 3,  "name": "Attitude Girl DP"},
        {"id": 4,  "name": "Aesthetic Girl DP"},
        {"id": 5,  "name": "Trending"},
    ]

    if not categories:
        msg = "❌ ERROR: Could not fetch WordPress categories. Check your credentials."
        log(msg)
        send_telegram(msg)
        return

    log("Fetching keyword suggestions from Google...")
    keywords = collect_keywords(SEED_KEYWORDS, used_keywords)

    if not keywords:
        msg = "⚠️ No fresh keywords found. Exiting."
        log(msg)
        send_telegram(msg)
        return

    random.shuffle(keywords)
    selected = keywords[:posts_to_create]
    STATS.keywords_used = selected
    log(f"Selected {len(selected)} keywords for this run")

    if not dry_run:
        all_media = fetch_all_wp_media()
        if not all_media:
            msg = "❌ ERROR: Could not fetch WP media. Check your credentials."
            log(msg)
            send_telegram(msg)
            return
    else:
        all_media = [
            {"id": i, "source_url": f"https://unityimage.com/wp-content/img{i}.jpg", "alt_text": "girl dp"}
            for i in range(1, 500)
        ]

    for kw in selected:
        log(f"\n--- Keyword: '{kw}' ---")

        title       = generate_title(kw)
        subheadings = fetch_subheadings_from_google(kw, count=5)
        category_id = match_category(title, categories)
        intro       = generate_intro(kw)
        focus_kw    = title_case_keyword(kw)
        meta_desc   = generate_meta_description(intro)

        log(f"  Title      : {title}")
        log(f"  Subheadings: {' | '.join(subheadings)}")
        log(f"  Focus KW   : {focus_kw}")
        log(f"  Meta Desc  : {meta_desc[:80]}...")

        html_content = build_html_gallery(
            subheadings, all_media, IMAGES_PER_HEADING, kw, intro
        )

        cat_name = next((c["name"] for c in categories if c["id"] == category_id), "Unknown")

        if dry_run:
            log(f"  [DRY RUN] Would create : '{title}'")
            log(f"  [DRY RUN] Category     : {cat_name} (ID={category_id})")
            log(f"  [DRY RUN] Sections     : {len(subheadings)}")
            log(f"  [DRY RUN] HTML size    : {len(html_content)} chars")

            STATS.posts_created.append({
                "title":    title,
                "link":     "https://unityimage.com/?p=DRY_RUN",
                "category": cat_name,
                "keyword":  kw,
            })
        else:
            # NO featured image passed — removed in v12
            post_id, post_link = create_wp_post(
                title, html_content, category_id, focus_kw, meta_desc
            )

            if post_id:
                log(f"  ✓ Post created! ID={post_id} | Category={cat_name} | {post_link}")
                save_used_keyword(kw)

                STATS.posts_created.append({
                    "title":    title,
                    "link":     post_link,
                    "category": cat_name,
                    "keyword":  kw,
                })

                if POST_STATUS == "publish" and post_link:
                    request_google_indexing(post_link)

            else:
                log(f"  ✗ Failed to create post for '{kw}'")
                STATS.posts_failed.append(kw)

        time.sleep(2)

    # ── Final Summary ──────────────────────────────────────
    log(f"\n{'='*60}")
    log(f"Done | Created: {len(STATS.posts_created)} | Failed: {len(STATS.posts_failed)}")
    log(f"{'='*60}\n")

    # Send final Telegram report
    summary = build_telegram_summary(STATS)
    send_telegram(summary)


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto WordPress Post Creator v12")
    parser.add_argument("--posts",   type=int,           default=POSTS_PER_RUN, help="Number of posts to create")
    parser.add_argument("--dry-run", action="store_true",                        help="Preview without posting to WordPress")
    args = parser.parse_args()

    run(posts_to_create=args.posts, dry_run=args.dry_run)