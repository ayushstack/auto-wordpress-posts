"""
auto_posts.py — Fully Automatic WordPress Post Creator (v14)
============================================================
Changes from v13:
  ✅ Intros loaded from intros.txt
  ✅ Meta descriptions loaded from meta_descriptions.txt
  ✅ Title templates loaded from title_templates.txt
  ✅ Subheading fallbacks loaded from subheading_fallbacks.txt
  ✅ Focus keyword = clean keyword only (no title template wrapping)
  ✅ Meta description uses keyword as clean title (no brackets/numbers)
  ✅ Zero hardcoded content — everything lives in .txt files

File structure:
  auto_posts.py              ← this script (settings only)
  keywords.txt               ← your seed keywords
  intros.txt                 ← intro paragraph templates (split by ---)
  meta_descriptions.txt      ← meta description templates (split by ---)
  title_templates.txt        ← title templates (one per line)
  subheading_fallbacks.txt   ← fallback sets (one set per line, comma separated)
  service_account.json       ← Google Indexing API key
"""

import requests
import random
import re
import time
import argparse
import os
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

WP_URL             = "https://unityimage.com/wp-json/wp/v2"
USERNAME           = os.environ.get("WP_USERNAME", "your_wp_username")
APP_PASSWORD       = os.environ.get("WP_APP_PASSWORD", "your_app_password")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "your_token")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "your_chat_id")

# --- Post settings ---
POSTS_PER_RUN      = 1
IMAGES_PER_HEADING = 10
POST_STATUS        = "draft"   # "draft" or "publish"

# --- Google Indexing ---
SERVICE_ACCOUNT_FILE = "service_account.json"

# --- Fallback category ---
FALLBACK_CATEGORY = "Trending"

# --- All content files ---
KEYWORDS_FILE           = "keywords.txt"
INTROS_FILE             = "intros.txt"
META_DESCRIPTIONS_FILE  = "meta_descriptions.txt"
TITLE_TEMPLATES_FILE    = "title_templates.txt"
SUBHEADING_FALLBACK_FILE = "subheading_fallbacks.txt"

# --- Tracking files ---
USED_KEYWORDS_FILE = "used_keywords.txt"
LOG_FILE           = "logs/auto_posts.log"

# --- Low keywords warning threshold ---
LOW_KEYWORDS_THRESHOLD = 10

AUTH = (USERNAME, APP_PASSWORD)


# ============================================================
# RUN STATS
# ============================================================

class RunStats:
    def __init__(self):
        self.start_time    = datetime.now()
        self.posts_created = []
        self.posts_failed  = []
        self.indexed       = []
        self.index_failed  = []
        self.keywords_used = []
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
# FILE LOADERS
# ============================================================

def load_text_list(filepath, split_by="---"):
    """
    Loads a .txt file and returns a list of non-empty entries.
    If split_by is set, splits the file by that separator (for multi-line blocks).
    If split_by is None, returns one entry per line.
    """
    if not os.path.exists(filepath):
        log(f"  ⚠ File not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if split_by:
        entries = [e.strip() for e in content.split(split_by) if e.strip()]
    else:
        entries = [line.strip() for line in content.splitlines()
                   if line.strip() and not line.strip().startswith("#")]

    log(f"  Loaded {len(entries)} entries from {filepath}")
    return entries


def load_subheading_fallbacks():
    """
    Loads subheading_fallbacks.txt.
    Each line is one fallback set, words separated by comma.
    Returns a list of lists.
    """
    lines = load_text_list(SUBHEADING_FALLBACK_FILE, split_by=None)
    result = []
    for line in lines:
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if parts:
            result.append(parts)
    log(f"  Loaded {len(result)} subheading fallback sets")
    return result


def load_keywords_from_file():
    """
    Reads seed keywords from keywords.txt.
    Lines starting with # and empty lines are ignored.
    """
    seeds = load_text_list(KEYWORDS_FILE, split_by=None)
    log(f"  Loaded {len(seeds)} seed keywords from {KEYWORDS_FILE}")
    return seeds


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("  ⚠ Telegram not configured — skipping notification")
        return

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
    run_date = stats.start_time.strftime("%d %b %Y, %I:%M %p IST")
    mode     = "🔍 DRY RUN" if stats.dry_run else "🚀 LIVE RUN"

    lines = [
        "<b>🤖 Auto Posts Report</b>",
        f"<b>Date:</b> {run_date}",
        f"<b>Mode:</b> {mode}",
        f"<b>Time Taken:</b> {stats.elapsed()}",
        "",
        "<b>📊 Summary</b>",
        f"✅ Posts Created   : <b>{len(stats.posts_created)}</b>",
        f"❌ Posts Failed    : <b>{len(stats.posts_failed)}</b>",
        f"🔍 Indexed (Google): <b>{len(stats.indexed)}</b>",
        f"⚠️ Index Failed    : <b>{len(stats.index_failed)}</b>",
        "",
    ]

    if stats.posts_created:
        lines.append("<b>📝 Posts Created:</b>")
        for i, p in enumerate(stats.posts_created, 1):
            lines.append(
                f"{i}. <b>{p['title']}</b>\n"
                f"   📂 {p['category']} | 🔑 {p['keyword']}\n"
                f"   🔗 <a href=\"{p['link']}\">{p['link']}</a>"
            )
        lines.append("")

    if stats.posts_failed:
        lines.append("<b>❌ Failed Keywords:</b>")
        for kw in stats.posts_failed:
            lines.append(f"  • {kw}")
        lines.append("")

    if stats.indexed:
        lines.append("<b>🔍 Google Indexing Requested:</b>")
        for url in stats.indexed:
            lines.append(f"  • {url}")
        lines.append("")

    if stats.index_failed:
        lines.append("<b>⚠️ Indexing Failed:</b>")
        for url in stats.index_failed:
            lines.append(f"  • {url}")
        lines.append("")

    lines.append("─────────────────────")
    lines.append("<i>unityimage.com | Auto Posts v14</i>")

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
# LOW KEYWORDS ALERT
# ============================================================

def check_keywords_low(fresh_count):
    if fresh_count == 0:
        send_telegram(
            "🚨 <b>Keywords Exhausted!</b>\n\n"
            "All keywords in <code>keywords.txt</code> have been used up.\n"
            "No new posts can be created until you add more.\n\n"
            "👉 <b>What to do:</b>\n"
            "1. Open <code>keywords.txt</code> in your project\n"
            "2. Add new keywords (one per line)\n"
            "3. Save → commit → push to GitHub\n\n"
            "Script will resume automatically on next run. ✅"
        )
    elif fresh_count <= LOW_KEYWORDS_THRESHOLD:
        send_telegram(
            f"⚠️ <b>Keywords Running Low!</b>\n\n"
            f"Only <b>{fresh_count}</b> fresh keywords remaining.\n\n"
            f"👉 Please add more keywords to <code>keywords.txt</code> "
            f"and push to GitHub soon to avoid interruption."
        )


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


def collect_keywords(used_keywords):
    seeds = load_keywords_from_file()

    if not seeds:
        log("  No seed keywords found in keywords.txt")
        return []

    all_kws = []
    for seed in seeds:
        suggestions = fetch_autocomplete(seed)
        log(f"  Seed '{seed}' → {len(suggestions)} suggestions")
        all_kws.extend(suggestions)
        time.sleep(0.5)

    all_kws.extend(seeds)

    seen, unique = set(), []
    for kw in all_kws:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    fresh = [kw for kw in unique if kw not in used_keywords and len(kw.split()) >= 3]
    log(f"  Total fresh keywords available: {len(fresh)}")

    check_keywords_low(len(fresh))

    return fresh


# ============================================================
# TITLE CASE HELPER
# ============================================================

def title_case_keyword(kw):
    """
    Converts keyword to title case.
    e.g. 'hidden face girl dp' → 'Hidden Face Girl DP'
    """
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
# TITLE GENERATOR — loads from title_templates.txt
# ============================================================

def generate_title(kw):
    """
    Picks a random title template from title_templates.txt
    and replaces {kw} with the title-cased keyword.
    """
    templates = load_text_list(TITLE_TEMPLATES_FILE, split_by=None)

    if not templates:
        # Hard fallback if file is missing
        log("  ⚠ title_templates.txt empty or missing — using fallback")
        templates = ["Best {kw} HD Images Free Download"]

    template = random.choice(templates)
    return template.replace("{kw}", title_case_keyword(kw))


# ============================================================
# FOCUS KEYWORD — clean keyword only, no template wrapping
# ============================================================

def generate_focus_keyword(kw):
    """
    Returns only the clean title-cased keyword.
    e.g. 'hidden face girl dp' → 'Hidden Face Girl DP'
    No numbers, no brackets, no template text.
    This is set as the Yoast SEO focus keyphrase.
    """
    return title_case_keyword(kw)


# ============================================================
# INTRO GENERATOR — loads from intros.txt
# ============================================================

def generate_intro(keyword):
    """
    Picks a random intro from intros.txt (blocks split by ---).
    Replaces {topic} with the title-cased keyword.
    """
    intros = load_text_list(INTROS_FILE, split_by="---")

    if not intros:
        log("  ⚠ intros.txt empty or missing — using fallback")
        intros = [
            "Welcome to the best {topic} collection available for free download in HD quality."
        ]

    pretty   = title_case_keyword(keyword)
    template = random.choice(intros)
    intro    = template.replace("{topic}", pretty)
    log(f"  ✓ Intro generated ({len(intro)} chars)")
    return intro


# ============================================================
# META DESCRIPTION — loads from meta_descriptions.txt
# ============================================================

def generate_meta_description(keyword):
    """
    Picks a random meta description from meta_descriptions.txt.
    Replaces {topic} with the clean title-cased keyword.
    Truncates to 155 chars max for SEO.
    """
    descriptions = load_text_list(META_DESCRIPTIONS_FILE, split_by="---")

    if not descriptions:
        log("  ⚠ meta_descriptions.txt empty or missing — using fallback")
        descriptions = [
            "Download the best {topic} HD images free for Instagram and WhatsApp."
        ]

    pretty   = title_case_keyword(keyword)
    template = random.choice(descriptions)
    meta     = template.replace("{topic}", pretty).strip()

    # Truncate to 155 chars for SEO
    if len(meta) > 155:
        meta = meta[:152] + "..."

    log(f"  ✓ Meta description ({len(meta)} chars): {meta[:60]}...")
    return meta


# ============================================================
# SUBHEADINGS — loads fallbacks from subheading_fallbacks.txt
# ============================================================

def fetch_subheadings_from_google(keyword, count=5):
    """
    Fetches subheadings from Google Autocomplete.
    Falls back to subheading_fallbacks.txt if not enough results.
    """
    log(f"  Fetching subheadings from Google for: '{keyword}'")
    suggestions = fetch_autocomplete(keyword)

    result = []
    for s in suggestions:
        result.append(title_case_keyword(s))
        if len(result) >= count:
            break

    log(f"  Google returned {len(result)} subheading suggestions")

    if len(result) < count:
        fallback_sets = load_subheading_fallbacks()

        if not fallback_sets:
            # Hard fallback if file missing
            fallback_sets = [["Stylish", "Cute", "Aesthetic", "Attitude", "Sad"]]

        modifier_set = random.choice(fallback_sets)
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
        log(f"  '{FALLBACK_CATEGORY}' not found — using first category")
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
    data = {
        "title":      title,
        "content":    content,
        "status":     POST_STATUS,
        "categories": [category_id],
        "meta": {
            "_yoast_wpseo_focuskw":  focus_kw,   # clean keyword only
            "_yoast_wpseo_metadesc": meta_desc,   # from meta_descriptions.txt
        }
    }
    try:
        r      = requests.post(f"{WP_URL}/posts", json=data, auth=AUTH, timeout=30)
        result = r.json()

        if r.status_code not in (200, 201):
            log(f"  WP API error {r.status_code}")
            log(f"  WP error code   : {result.get('code', 'unknown')}")
            log(f"  WP error message: {result.get('message', 'unknown')}")
            log(f"  WP error data   : {result.get('data', {})}")
            send_telegram(
                f"\u274c <b>Post Creation Failed</b>\n\n"
                f"<b>Status:</b> {r.status_code}\n"
                f"<b>Code:</b> {result.get('code', 'unknown')}\n"
                f"<b>Message:</b> {result.get('message', 'unknown')}\n"
                f"<b>Title:</b> {data['title']}"
            )
            return None, ""

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
    log(f"Auto Posts v14 | target={posts_to_create} posts | dry_run={dry_run}")
    log("=" * 60)

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
        {"id": 1, "name": "Hidden Face Girl Pic"},
        {"id": 2, "name": "Sad Girl DP"},
        {"id": 3, "name": "Attitude Girl DP"},
        {"id": 4, "name": "Aesthetic Girl DP"},
        {"id": 5, "name": "Trending"},
    ]

    if not categories:
        msg = "❌ ERROR: Could not fetch WordPress categories. Check your credentials."
        log(msg)
        send_telegram(msg)
        return

    log("Fetching keyword suggestions from Google...")
    keywords = collect_keywords(used_keywords)

    if not keywords:
        msg = (
            "🚨 <b>No fresh keywords found!</b>\n\n"
            "All keywords in <code>keywords.txt</code> are either used up or the file is empty.\n"
            "Please add new keywords to <code>keywords.txt</code> and push to GitHub."
        )
        log("No fresh keywords found. Exiting.")
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

        title     = generate_title(kw)
        focus_kw  = generate_focus_keyword(kw)     # clean keyword only → Yoast
        intro     = generate_intro(kw)             # from intros.txt
        meta_desc = generate_meta_description(kw)  # from meta_descriptions.txt

        subheadings = fetch_subheadings_from_google(kw, count=5)
        category_id = match_category(title, categories)

        log(f"  Title      : {title}")
        log(f"  Focus KW   : {focus_kw}")
        log(f"  Subheadings: {' | '.join(subheadings)}")
        log(f"  Meta Desc  : {meta_desc[:80]}...")

        html_content = build_html_gallery(
            subheadings, all_media, IMAGES_PER_HEADING, kw, intro
        )

        cat_name = next((c["name"] for c in categories if c["id"] == category_id), "Unknown")

        if dry_run:
            log(f"  [DRY RUN] Would create : '{title}'")
            log(f"  [DRY RUN] Focus KW     : {focus_kw}")
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

    log(f"\n{'='*60}")
    log(f"Done | Created: {len(STATS.posts_created)} | Failed: {len(STATS.posts_failed)}")
    log(f"{'='*60}\n")

    summary = build_telegram_summary(STATS)
    send_telegram(summary)


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto WordPress Post Creator v14")
    parser.add_argument("--posts",   type=int,           default=POSTS_PER_RUN, help="Number of posts to create")
    parser.add_argument("--dry-run", action="store_true",                        help="Preview without posting to WordPress")
    args = parser.parse_args()

    run(posts_to_create=args.posts, dry_run=args.dry_run)