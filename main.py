import sqlite3, os, asyncio
from datetime import datetime
from urllib.parse import urlparse
from nicegui import app, ui, background_tasks
from openai import OpenAI
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv(dotenv_path="env.txt")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

# --- BRANDING & STYLES ---
ui.query('body').style('background-color: #ffffff; color: #333333; font-family: "Helvetica Neue", Arial, sans-serif;')

class MagicRundownApp:
    def __init__(self):
        self.db_path = 'magic_rundown.db'
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self.active_category = 'general' 
        self.migrate_db() 
        self.render_ui()

    def migrate_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Ensure radio_scripts supports 8 columns: id, tease, full_story, source_name, link, timestamp, is_aired, category
        c.execute('''CREATE TABLE IF NOT EXISTS radio_scripts
                     (id TEXT PRIMARY KEY, tease TEXT, full_story TEXT, 
                      source_name TEXT, link TEXT, timestamp DATETIME, 
                      is_aired INTEGER DEFAULT 0, category TEXT DEFAULT 'general')''')
        conn.commit()
        conn.close()

    def get_dates(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT DISTINCT date(timestamp) FROM selected_stories ORDER BY timestamp DESC")
            dates = [r[0] for r in c.fetchall()]
            conn.close()
            if self.current_date not in dates:
                dates.insert(0, self.current_date)
            return dates
        except: return [self.current_date]

    def toggle_aired(self, s_id, current_val, title, summary, score, link):
        new_val = 1 if current_val == 0 else 0
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE radio_scripts SET is_aired = ? WHERE id = ?", (new_val, s_id))
        conn.commit()
        conn.close()
        self.story_list.refresh()
        self.show_details(title, summary, score, link, s_id)

    async def generate_prep(self, title, summary, link, s_id, score, button):
        button.disable()
        # ... spinner logic ...
        
        prompt = f"Write a 20-word TEASE, then '###', then a 100-word FULL STORY using ellipses (...) for: {title}. Details: {summary}"
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.3
            ))
            content = response.choices[0].message.content.strip()
            
            # Split using the new reliable delimiter
            if "###" in content:
                parts = content.split("###")
                tease = parts[0].strip()
                story = parts[1].strip()
            else:
                tease = "Check out this story..."
                story = content

            # ... database save logic (Ensure you use all 8 columns!) ...
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            # FIX: Exactly 8 columns to match schema
            c.execute("INSERT OR REPLACE INTO radio_scripts VALUES (?, ?, ?, ?, ?, datetime('now'), 0, ?)",
                      (s_id, tease, story, domain, link, self.active_category))
            conn.commit()
            conn.close()
            self.show_details(title, summary, score, link, s_id)
            self.story_list.refresh()
        finally:
            loading.delete()

    def show_details(self, title, summary, score, link, s_id):
        self.detail_pane.clear()
        domain = urlparse(link).netloc.replace('www.', '')
        with self.detail_pane:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT tease, full_story, is_aired FROM radio_scripts WHERE id = ?", (s_id,))
            saved = c.fetchone()
            conn.close()

            if saved:
                tease, story, is_aired = saved
                with ui.card().classes('w-full p-8 bg-white border-t-8 border-[#8B1D22] shadow-lg'):
                    ui.label(title).classes('text-3xl font-black text-gray-900 mb-6 uppercase')
                    btn_text = 'MARK AS UNUSED' if is_aired else 'MARK AS AIRED'
                    ui.button(btn_text, on_click=lambda: self.toggle_aired(s_id, is_aired, title, summary, score, link)) \
                        .style(f'background-color: {"#cbd5e1" if is_aired else "#8B1D22"}; color: white;').classes('mb-8 font-bold px-6')
                    ui.label('TEASE').classes('text-[#8B1D22] font-black text-xs tracking-widest')
                    ui.label(tease).classes('text-xl font-medium mb-10 text-gray-800 italic')
                    ui.label('FULL STORY').classes('text-[#8B1D22] font-black text-xs tracking-widest')
                    ui.markdown(story).classes('text-lg leading-relaxed text-gray-700')
                    ui.link(f"SOURCE: {domain.upper()}", link, new_tab=True).classes('text-[#8B1D22] font-bold underline mt-4 block')
            else:
                with ui.card().classes('w-full p-8 bg-white shadow-md border-l-8 border-gray-200'):
                    ui.label(title).classes('text-2xl font-bold mb-4')
                    ui.label(summary[:500] + "...").classes('text-gray-500 mb-8 italic')
                    ui.button('MANUALLY GENERATE MAGIC 96.7 PREP', on_click=lambda e: self.generate_prep(title, summary, link, s_id, score, e.sender)) \
                        .style('background-color: #333333; color: white;').classes('w-full py-4 font-bold rounded-lg')

    @ui.refreshable
    def story_list(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT score, title, summary, link, id FROM selected_stories WHERE date(timestamp) = ? AND category = ? ORDER BY score DESC", (self.current_date, self.active_category))
        stories = c.fetchall()
        c.execute("SELECT id, is_aired FROM radio_scripts")
        status_map = {r[0]: r[1] for r in c.fetchall()}
        conn.close()

        with ui.column().classes('w-full gap-3'):
            for score, title, summary, link, s_id in stories:
                is_prepped = s_id in status_map
                is_aired = status_map.get(s_id, 0) == 1
                color = "#8B1D22" if score >= 8 else "#cbd5e1"
                opacity = 'opacity-40' if is_aired else 'opacity-100'
                with ui.card().classes(f'w-full bg-white border-l-8 cursor-pointer hover:shadow-md p-4 {opacity}').style(f'border-color: {color}') \
                    .on('click', lambda t=title, s=summary, sc=score, l=link, sid=s_id: self.show_details(t, s, sc, l, sid)):
                    with ui.row().classes('w-full no-wrap items-start justify-between'):
                        with ui.column().classes('w-10/12'):
                            ui.label(title).classes('font-bold text-gray-800 text-base leading-tight')
                            with ui.row().classes('items-center gap-2 mt-1'):
                                if is_aired: ui.label('AIRED').classes('text-[10px] font-black text-white bg-red-600 px-1 rounded')
                                elif is_prepped: ui.label('PREPPED').classes('text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1 rounded')
                        ui.badge(str(score), color=color).classes('p-2 font-black') # RESTORED THE RATING BADGE

    def render_ui(self):
        with ui.header().classes('bg-white p-4 border-b-4 border-[#8B1D22] items-center justify-between shadow-sm'):
            ui.label('MAGIC 96.7 RUNDOWN').classes('text-3xl font-black text-[#333333] tracking-tighter')
            with ui.row().classes('items-center gap-4'):
                tabs = ui.tabs().classes('text-[#8B1D22]')
                with tabs:
                    ui.tab('general', label='GENERAL')
                    ui.tab('celeb', label='CELEBRITY')
                tabs.on('update:model-value', lambda e: [setattr(self, 'active_category', e.args), self.story_list.refresh(), self.detail_pane.clear()])
                ui.select(self.get_dates(), value=self.current_date, on_change=lambda e: [setattr(self, 'current_date', e.value), self.story_list.refresh()]).classes('w-44 border rounded')

        with ui.row().classes('w-full h-screen no-wrap'):
            with ui.column().classes('w-2/5 p-6 bg-slate-50 border-r h-full overflow-y-auto'):
                self.story_list()
            with ui.column().classes('w-3/5 p-12 bg-white h-full overflow-y-auto'):
                self.detail_pane = ui.column().classes('w-full')

app_instance = MagicRundownApp()
ui.run(title="Magic 96.7 Rundown", port=8083, reload=False)