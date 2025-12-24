import feedparser
import sqlite3
import requests
import ssl
import time
import trafilatura
import re
from datetime import datetime, timedelta
import urllib3

# Disable the SSL warnings for the Mac LibreSSL issue
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
FEEDS = [
    'https://www.wmur.com/topstories-rss',
    'https://www.wcax.com/arc/outboundfeeds/rss/',
    'https://www.mentalfloss.com/api/content/rss',
    'https://www.thetopicalfruit.com/feed/',
    'https://today.yougov.com/rss/all/',
    'https://wallethub.com/feed/all',
    'https://people.com/feed',
    'https://abc7.com/feed/',
    'https://www.reddit.com/r/nottheonion/.rss',
    'https://www.reddit.com/r/upliftingnews/.rss',
    'https://www.reddit.com/r/LifeProTips/.rss',
    'https://apnews.com/external/import-feed.rss',
    'https://rss.nytimes.com/services/xml/rss/nyt/Upshot.xml',
    'https://feeds.npr.org/1001/rss.xml',
    'https://feeds.npr.org/1007/rss.xml',
    'https://www.realsimple.com/rss/all',
    'https://www.goodnewsnetwork.org/feed/',
    'https://www.eonline.com/feeds/rss/topstories',
    'https://variety.com/feed/',
    'https://pitchfork.com/feed/feed-news/rss'
]

def init_db():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stories
                 (id TEXT PRIMARY KEY, title TEXT, summary TEXT, link TEXT, 
                  timestamp DATETIME, raw_date TEXT, category TEXT)''')
    conn.commit()
    return conn

def extract_reddit_target_url(entry):
    if 'reddit.com' not in entry.link: return entry.link
    summary = entry.get('summary', '')
    links = re.findall(r'href="(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)"', summary)
    for l in links:
        if 'reddit.com' not in l: return l
    return entry.link

def get_full_article_text(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        content = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return content if content else ""
    except: return ""

def harvest():
    conn = init_db()
    c = conn.cursor()
    now = datetime.now()
    cutoff = now - timedelta(days=2) 
    
    total_added = 0
    print(f"\n🚀 STARTING DEEP HARVEST: {now.strftime('%H:%M:%S')}")
    print("-" * 65)
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})

    for url in FEEDS:
        domain = url.split('/')[2].replace('www.', '')
        # ALL STORIES NOW DEFAULT TO 'general'
        category = 'general' 
        print(f"📡 Checking {domain:.<30}", end=" ", flush=True)
        
        try:
            response = session.get(url, timeout=10, verify=False)
            feed = feedparser.parse(response.text)
        except Exception:
            print("FAILED (Timeout)")
            continue
            
        feed_added = 0
        process_limit = 15 if "reddit.com" in url else 30
        
        for entry in feed.entries[:process_limit]:
            real_news_link = extract_reddit_target_url(entry)
            s_id = entry.get('id', real_news_link)
            
            c.execute("SELECT id FROM stories WHERE id = ?", (s_id,))
            if c.fetchone(): continue

            pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)) if 'published_parsed' in entry else now
            if pub_date < cutoff: continue

            print(f".", end="", flush=True) 
            full_text = get_full_article_text(real_news_link)
            final_content = full_text if (full_text and len(full_text) > 150) else entry.get('summary', '')

            try:
                # Every story is inserted with 'general' category
                c.execute("INSERT OR REPLACE INTO stories VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (s_id, entry.title, final_content, real_news_link, 
                           pub_date.strftime('%Y-%m-%d %H:%M:%S'), 
                           pub_date.strftime('%Y-%m-%d'), category))
                feed_added += 1
            except: continue
        
        total_added += feed_added
        print(f" Added {feed_added}")
    
    conn.commit()
    conn.close()
    print("-" * 65)
    print(f"✅ HARVEST COMPLETE: {total_added} stories added to GENERAL.")

if __name__ == "__main__":
    harvest()
    cleanup_old_data()

def cleanup_old_data():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    # Delete stories older than 7 days to keep the DB small
    c.execute("DELETE FROM stories WHERE timestamp < datetime('now', '-7 days')")
    c.execute("DELETE FROM selected_stories WHERE timestamp < datetime('now', '-7 days')")
    # Physically shrink the file
    c.execute("VACUUM")
    conn.commit()
    conn.close()