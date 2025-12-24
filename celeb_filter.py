import sqlite3
import os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(dotenv_path="env.txt")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

def init_winners():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    
    # 1. Ensure the table exists
    c.execute('''CREATE TABLE IF NOT EXISTS selected_stories
                 (id TEXT PRIMARY KEY, title TEXT, score INTEGER, 
                  summary TEXT, link TEXT, timestamp DATETIME)''')
    
    # 2. MIGRATION: Add category column if it is missing
    try:
        c.execute("ALTER TABLE selected_stories ADD COLUMN category TEXT DEFAULT 'news'")
        print("🛠 Database Migrated: Added 'category' column.")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    return conn

def run_celeb_filter():
    conn = init_winners()
    c = conn.cursor()
    
    # Only select stories tagged as 'celeb' that haven't been scored yet
    query = """
        SELECT id, title, summary, link, timestamp FROM stories 
        WHERE category = 'celeb' AND id NOT IN (SELECT id FROM selected_stories)
        ORDER BY timestamp DESC
    """
    c.execute(query)
    raw_stories = c.fetchall()
    
    if not raw_stories:
        print("\n☕️ NO NEW CELEB STORIES: Everything is already scored.")
        return

    # --- THE HARD REJECT LIST ---
    # Skips these before spending any AI credits
    BANNED_PHRASES = [
        "everything to know", "lookalikes", "swears by", "face mist", 
        "deal", "discount", "sale", "where to buy", "shop the", 
        "must-have", "gift guide", "skincare routine", "amazon", "walmart",
        "double take", "designer lookalikes", "swears this"
    ]

    print(f"\n💎 AI GOSSIP SCORING: {len(raw_stories)} candidate stories found.")
    print("-" * 50)

    for s_id, title, summary, link, timestamp in raw_stories:
        
        # 1. PRE-FILTER: Check against banned phrases
        if any(phrase in title.lower() for phrase in BANNED_PHRASES):
            print(f"⏩ Skipping SEO-Bait/Shopping: {title[:50]}...")
            continue

        # 2. AI SCORING: The "Elite Trash" Prompt
        prompt = (
            "Rank this celebrity story 1-10 for a dishy morning radio segment (Moms 35-54). "
            "10: This is either:"
            "A) ELITE TRASH (Scandals, major breakups, A-list feuds, shocking reveals, 'wild' behavior). "
            "Or B) Major/Interesting ENT NEWS (Massive casting like James Bond/Marvel, a beloved show finale, "
            "huge award wins, or a trailer for a giant franchise). "
            "8-9: Actors/Musician news"
            "7-8: Standard (Movie trailers, award announcements, harmless A-list updates). "
            "1: AUTOMATIC REJECT (Shopping deals, product endorsements, 'Everything to know' guides, politics NOT celeb related,"
            "lookalike stories, or anything about 'discounts'). "
            "We want drama, not a shopping catalog."
            "Subtract 4 from a score if it's a recipe."
            "Be extremely critical and harsh; be stingy with 10/10s."
            "Return ONLY the number."
        )

        try:
            print(f"🧐 Gossip Score: {title[:60]}...", end=" ", flush=True)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + f"\nSTORY: {title}"}],
                max_tokens=2, 
                temperature=0.2
            )
            
            score_text = response.choices[0].message.content.strip()
            score = int(''.join(filter(str.isdigit, score_text)))
            
            print(f"Result: {score}/10")
            
            # 3. SAVE: Includes the 'celeb' category tag for the tabbed dashboard
            c.execute("""
                INSERT OR REPLACE INTO selected_stories 
                (id, title, score, summary, link, timestamp, category) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (s_id, title, score, summary, link, timestamp, 'celeb'))
            conn.commit()
            
        except Exception as e:
            print(f"Error: {e}")
            continue

    conn.close()
    print("-" * 50)
    print("✅ CELEB SCORING COMPLETE.")
if __name__ == "__main__":
    run_celeb_filter()