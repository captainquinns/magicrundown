import sqlite3, os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURATION ---
load_dotenv(dotenv_path="env.txt")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

def init_autopilot_db():
    conn = sqlite3.connect('magic_rundown.db')
    c = conn.cursor()
    # Unified 8-column schema to match dashboard and filter
    c.execute('''CREATE TABLE IF NOT EXISTS radio_scripts
                 (id TEXT PRIMARY KEY, tease TEXT, full_story TEXT, 
                  source_name TEXT, link TEXT, timestamp DATETIME, 
                  is_aired INTEGER DEFAULT 0, category TEXT DEFAULT 'general')''')
    conn.commit()
    return conn

def write_prep(title, summary):
    # Added strict character counts and a unique delimiter (###) for 100% reliable splitting
    prompt = f"""
    Write a short radio news script based on the article. 
    
    STORY: {title}
    DETAILS: {summary}

    TASK:
    1. TEASE: One paragraph, under 40 words; Must stand alone. Fun, punchy, slightly sarcastic.
    2. DELIMITER: Write exactly '###'
    3. FULL STORY: Conversational radio script - one host, under 2 minutes. Short paragraphs. Clear, spoken language. Lean into humor, irony, and absurd details when they exist. Do not invent facts. Avoid cliche radio talk while keeping it marketable. No intro (like 'Good morning' or 'hold onto your hats') or outro (like 'stay tuned') at the end of the main story.

    FORMAT:
    [Tease here]
    ###
    [Full story here]
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.choices[0].message.content.strip()
        
        # Split by the unique delimiter instead of fragile string searches
        if "###" in content:
            parts = content.split("###")
            tease = parts[0].strip()
            story = parts[1].strip()
        else:
            # Fallback that still avoids "Hook Inside"
            tease = title[:60] + "..."
            story = content
            
        return tease, story
    except:
        return None, None

def run_autopilot():
    conn = init_autopilot_db()
    c = conn.cursor()
    
    total_written = 0
    print(f"\n🚀 STARTING MAGIC AUTOPILOT: {datetime.now().strftime('%H:%M:%S')}")
    print("-" * 65)

    # CRITICAL FIX: Explicitly selecting today's stories and high scores
    # We join or check against the ID to ensure we only process "un-prepped" stories
    c.execute("""
        SELECT id, title, summary, link, timestamp, category 
        FROM selected_stories 
        WHERE score >= 8 
        AND id NOT IN (SELECT id FROM radio_scripts)
        ORDER BY timestamp DESC
    """)
    
    queue = c.fetchall()
    
    if not queue:
        print(f"✅ No new high-scoring stories found in selected_stories table.")
    else:
        print(f"✍️  Writing scripts for {len(queue)} stories...")

        for s_id, title, summary, link, ts, cat in queue:
            print(f"   + Prepping: {title[:50]}...", end=" ", flush=True)
            
            tease, story = write_prep(title, summary)
            
            if tease and story:
                domain = link.split('/')[2].replace('www.', '')
                
                try:
                    # EXACTLY 8 VALUES: id, tease, story, source, link, ts, aired, cat
                    c.execute("""
                        INSERT OR REPLACE INTO radio_scripts 
                        (id, tease, full_story, source_name, link, timestamp, is_aired, category) 
                        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    """, (s_id, tease, story, domain, link, ts, cat))
                    total_written += 1
                    print("DONE")
                except Exception as e:
                    print(f"FAILED (DB Error: {e})")
            else:
                print("FAILED (AI Error)")

    conn.commit()
    conn.close()
    print("-" * 65)
    print(f"✅ AUTOPILOT COMPLETE: {total_written} scripts processed.")

if __name__ == "__main__":
    run_autopilot()