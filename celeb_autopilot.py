import sqlite3
import os
from urllib.parse import urlparse
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURATION ---
load_dotenv(dotenv_path="env.txt")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

def init_script_table():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    
    # 1. Ensure the table exists
    c.execute('''CREATE TABLE IF NOT EXISTS radio_scripts
                 (id TEXT PRIMARY KEY, tease TEXT, full_story TEXT, 
                  source_name TEXT, link TEXT, timestamp DATETIME)''')
    
    # 2. MIGRATION: Add category column to scripts table if missing
    try:
        c.execute("ALTER TABLE radio_scripts ADD COLUMN category TEXT DEFAULT 'news'")
        print("🛠 Database Migrated: Added 'category' column to radio_scripts.")
    except sqlite3.OperationalError:
        pass # Already exists
        
    conn.commit()
    return conn

def run_celeb_autopilot():
    conn = init_script_table()
    c = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Grab Celeb stories scored 7-10 for today
    c.execute("""
        SELECT id, title, summary, link, score 
        FROM selected_stories 
        WHERE score >= 7 AND date(timestamp) = ? AND category = 'celeb'
        ORDER BY score DESC
    """, (today,))
    
    stories_to_prep = c.fetchall()
    
    if not stories_to_prep:
        print(f"📭 No Celeb stories (Score 7+) found for {today}.")
        return

    print(f"🚀 CELEB AUTOPILOT: Prepping {len(stories_to_prep)} gossip stories...")
    print("-" * 50)

    for s_id, title, summary, link, score in stories_to_prep:
        # Check if already prepped
        c.execute("SELECT id FROM radio_scripts WHERE id = ?", (s_id,))
        if c.fetchone():
            continue

        print(f"✍️ Writing ({score}/10): {title[:50]}...", end=" ", flush=True)

        domain = urlparse(link).netloc.replace('www.', '')
        
        # THE CELEB-SPECIFIC GOSSIP PROMPT
        prompt = f"""
        Act as a dishy entertainment reporter for Magic 96.7. 
        Write a celebrity news segment for our 'Hollywood Rundown' section.

        ARTICLE TITLE: {title}
        ARTICLE CONTENT: {summary}

        STRICT INSTRUCTIONS:
        1. Summarize into a 200-word "gossip-style" story... be conversational - prioritize humor.
        2. 100% FACTUAL. Only use what is in the text. No made-up rumors.
        3. If content is missing, write "STORY DATA MISSING".
        4. Write a high-energy "Coming up next" TEASE.
        5. DO NOT start teases with "get ready..."
        6. Conversational but not cringy.

        FORMAT:
        TEASE: [The Hook, brief summary, with a 'find out, next' style ending]
        FULL STORY: [The Dish, all details, funny, interesting]
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4  # Slightly higher for more "flavor" than hard news
            )
            raw = response.choices[0].message.content
            
            if "TEASE:" in raw and "FULL STORY:" in raw:
                tease = raw.split("TEASE:")[1].split("FULL STORY:")[0].strip()
                story = raw.split("FULL STORY:")[1].strip()
            else:
                tease = "Hollywood is buzzing..."
                story = raw

            # Store with the 'celeb' category tag
            c.execute("""
                INSERT OR REPLACE INTO radio_scripts 
                (id, tease, full_story, source_name, link, timestamp, category) 
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
            """, (s_id, tease, story, domain, link, 'celeb'))
            
            conn.commit()
            print("DONE.")

        except Exception as e:
            print(f"FAILED: {e}")

    conn.close()
    print("-" * 50)
    print("✅ Celeb Autopilot Complete.")

if __name__ == "__main__":
    run_celeb_autopilot()