import feedparser
import sqlite3
import urllib.request
import ssl
import time
import trafilatura
import re
from datetime import datetime, timedelta

# --- CELEB & GOSSIP FEEDS ---
CELEB_FEEDS = [
    'https://www.tmz.com/rss.xml',                    # Breaking scandals/legal
    'https://pagesix.com/feed/',                      # A-List drama & NYC gossip
    'https://theblast.com/feed/',                     # Legal/Court documents
    'https://radaronline.com/feed/',                  # Hard-hitting investigations
    'https://www.intouchweekly.com/feed/',            # Tabloid/Relationship drama
    'https://okmagazine.com/feed/',                   # Classic A-list gossip
    'https://starmagazine.com/feed/',                 # "Trashy" tabloid energy
    'https://www.dailymail.co.uk/tvshowbiz/index.rss',# High-volume dishy news
    'https://www.reddit.com/r/Fauxmoi/.rss',          # Elite insider blind items
    'https://www.reddit.com/r/popculturechat/.rss',   # Viral celebrity chatter
    'https://perezhilton.com/feed/',                  # Dishy commentary
    'https://www.thehollywoodgossip.com/feed/',       # Relationship & feud focus
    'https://people.com/rss/celebrity/news/feed.xml'  # PEOPLE (News-only branch)
    'https://nypost.com/rssfeeds/'
]
def init_db():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    # Migration: Ensure table has 7 columns for the 'category' tag
    try:
        c.execute("ALTER TABLE stories ADD COLUMN category TEXT DEFAULT 'news'")
    except:
        pass 
    c.execute('''CREATE TABLE IF NOT EXISTS stories
                 (id TEXT PRIMARY KEY, title TEXT, summary TEXT, link TEXT, timestamp DATETIME, raw_date TEXT, category TEXT)''')
    conn.commit()
    return conn

def extract_reddit_target_url(entry):
    if 'reddit.com' not in entry.link:
        return entry.link
    summary = entry.get('summary', '')
    links = re.findall(r'href="(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)"', summary)
    for l in links:
        if 'reddit.com' not in l:
            return l
    return entry.link

def get_full_article_text(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        content = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return content if content else ""
    except:
        return ""

def harvest_celeb():
    conn = init_db()
    c = conn.cursor()
    ssl_context = ssl._create_unverified_context()
    now = datetime.now()
    cutoff = now - timedelta(days=2) 
    
    total_added = 0
    print(f"\n✨ STARTING CELEB HARVEST: {now.strftime('%H:%M:%S')}")
    print("-" * 65)
    
    for url in CELEB_FEEDS:
        domain = url.split('/')[2].replace('www.', '')
        print(f"📸 Checking {domain:.<30}", end=" ", flush=True)
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
                feed_data = response.read()
            feed = feedparser.parse(feed_data)
        except Exception:
            print("FAILED (Network)")
            continue
            
        feed_added = 0
        for entry in feed.entries:
            title = entry.title
            real_news_link = extract_reddit_target_url(entry)
            s_id = entry.get('id', real_news_link)
            
            # Date Handling
            if 'published_parsed' in entry and entry.published_parsed:
                pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            else:
                pub_date = now
            
            if pub_date > now: pub_date = now 
            if pub_date < cutoff: continue

            # Check if exists
            c.execute("SELECT id FROM stories WHERE id = ?", (s_id,))
            if c.fetchone(): continue

            print(f".", end="", flush=True) 
            full_text = get_full_article_text(real_news_link)
            final_content = full_text if (full_text and len(full_text) > 150) else entry.get('summary', '')

            try:
                # IMPORTANT: category='celeb' is added here
                c.execute("INSERT OR REPLACE INTO stories VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (s_id, title, final_content, real_news_link, 
                           pub_date.strftime('%Y-%m-%d %H:%M:%S'), 
                           pub_date.strftime('%Y-%m-%d'), 'celeb'))
                feed_added += 1
            except Exception as e: 
                continue
        
        total_added += feed_added
        print(f" Added {feed_added}")
    
    conn.commit()
    conn.close()
    print("-" * 65)
    print(f"✅ CELEB HARVEST COMPLETE: {total_added} stories added.")

if __name__ == "__main__":
    harvest_celeb()