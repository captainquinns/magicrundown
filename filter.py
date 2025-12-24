import sqlite3
import os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURATION ---
load_dotenv(dotenv_path="env.txt")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

def init_filter_db():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    # Ensure selected_stories has the category column
    c.execute('''CREATE TABLE IF NOT EXISTS selected_stories
                 (id TEXT PRIMARY KEY, title TEXT, score INTEGER, 
                  summary TEXT, link TEXT, timestamp DATETIME, category TEXT)''')
    
    try:
        c.execute("ALTER TABLE selected_stories ADD COLUMN category TEXT DEFAULT 'general'")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    return conn

def score_story(title, summary, category):
    """Scores stories based on the Magic 96.7 demographic (Moms 35-54)."""
    
    # Adjusting the persona based on category for better scoring accuracy
    persona = "General News" if category == 'general' else "Celebrity/Entertainment News"
    
    prompt = f"""
    Act as a program director for Magic 96.7, a Hot AC station. 
    Our target audience is Women 35-54. 
    
    Category: {persona}
    Title: {title}
    Summary: {summary[:500]} 

   Act as producer for Brattleboro, VT morning show with an audience of women 35-54. Rate news topics 1-10.

10: ELITE. Absurd "Stupid News," viral surveys, home hacks (cooking/cleaning), money-saving tips, or relatable lifestyle drama.
1: TRASH. Politics, war, standard crime, depressing/cruel.

RULES:
- BE STINGY: Reserve 9-10 for "must-share" gold.
- PRIORITIZE: Home/lifestyle, money-wins, any surveys.
- DONT SKIP: High-value "stupid news" (bizarre/funny irony).
- BOOST: +2 for VT/NH/MA locations.
- Recipes and Clickbait/clearly sponsored posts get an automatic 1.

Return ONLY the number.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        score = int(response.choices[0].message.content.strip())
        return score
    except:
        return 1

def run_unified_filter():
    conn = init_filter_db()
    c = conn.cursor()
    
    # Process both categories: 'general' and 'celeb'
    categories = ['general', 'celeb']
    total_scored = 0

    print(f"\n🧠 STARTING UNIFIED FILTER: {datetime.now().strftime('%H:%M:%S')}")
    print("-" * 65)

    for cat in categories:
        # Grab stories that haven't been scored yet for this category
        c.execute("""
            SELECT id, title, summary, link, timestamp 
            FROM stories 
            WHERE category = ? AND id NOT IN (SELECT id FROM selected_stories)
        """, (cat,))
        
        queue = c.fetchall()
        if not queue:
            print(f"✅ {cat.upper():<10} | No new stories to score.")
            continue

        print(f"🧐 {cat.upper():<10} | Scoring {len(queue)} stories...")
        
        for s_id, title, summary, link, timestamp in queue:
            score = score_story(title, summary, cat)
            
            # Use the original harvest 'timestamp' to prevent Date Bleed
            c.execute("""
                INSERT OR REPLACE INTO selected_stories 
                (id, title, score, summary, link, timestamp, category) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (s_id, title, score, summary, link, timestamp, cat))
            
            total_scored += 1
            print(f"   [{score}/10] {title[:50]}...")

    conn.commit()
    conn.close()
    print("-" * 65)
    print(f"✅ FILTER COMPLETE: {total_scored} stories ranked and categorized.")

if __name__ == "__main__":
    run_unified_filter()