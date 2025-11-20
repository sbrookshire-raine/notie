import streamlit as st
import dropbox
import json
import hashlib
import re
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Notie Project Hub", layout="wide")

if "db_cache" not in st.session_state:
    st.session_state.db_cache = None

# 1. Load Secrets
try:
    APP_KEY = st.secrets["dropbox"]["app_key"]
    APP_SECRET = st.secrets["dropbox"]["app_secret"]
    REFRESH_TOKEN = st.secrets["dropbox"]["refresh_token"]
except Exception as e:
    st.error("❌ Secrets missing on Streamlit Cloud.")
    st.stop()

# 2. Connect to Dropbox
try:
    dbx = dropbox.Dropbox(
        app_key=APP_KEY,
        app_secret=APP_SECRET,
        oauth2_refresh_token=REFRESH_TOKEN
    )
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.stop()

DATA_FILENAME = "/notie_projects_db_v2.json"

# --- HELPER FUNCTIONS ---

def load_database():
    try:
        metadata, response = dbx.files_download(DATA_FILENAME)
        return json.loads(response.content.decode('utf-8'))
    except Exception:
        return {"projects": [], "imported_ids": [], "processed_files": []}

def save_database(data):
    json_bytes = json.dumps(data, indent=4).encode('utf-8')
    dbx.files_upload(
        json_bytes, 
        DATA_FILENAME, 
        mode=dropbox.files.WriteMode('overwrite')
    )

def generate_id(content):
    return hashlib.md5(content.encode()).hexdigest()

def extract_items_from_summary(summary_text):
    items = []
    if not summary_text: return items
    match = re.search(r'\[ITEMS\](.*?)(?=\[|$)', summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        lines = block.split('\n')
        for line in lines:
            clean_line = re.sub(r'^[-*•\d\.]+\s*', '', line).strip()
            if clean_line: items.append(clean_line)
    return items

def sync_new_files():
    """Scans Dropbox and generates a detailed log."""
    current_db = st.session_state.db_cache
    new_count = 0
    logs = [] # The detailed report
    
    try:
        result = dbx.files_list_folder("")
        
        for entry in result.entries:
            # 1. IGNORE SYSTEM FILES
            if not entry.name.endswith(".json") or "db" in entry.name:
                continue

            # 2. CHECK IF PROCESSED
            if entry.name in current_db['processed_files']:
                logs.append(f"⏭️ **{entry.name}**: Skipped (Filename already in database)")
                continue

            # 3. PROCESS NEW FILE
            logs.append(f"📥 **{entry.name}**: Reading...")
            md, res = dbx.files_download(entry.path_lower)
            try:
                data = json.loads(res.content.decode('utf-8'))
            except:
                logs.append(f"❌ **{entry.name}**: Corrupt JSON")
                continue
            
            notes = data.get("notes", data) if isinstance(data, dict) else data
            if isinstance(notes, dict): notes = [notes]

            file_new_tasks = 0
            for note in notes:
                notie_id = note.get('id')
                note_name = note.get('name', 'Untitled')
                
                # CHECK ID DUPLICATION
                if notie_id in current_db.get('imported_ids', []):
                    # We skipped this specific note
                    continue

                # EXTRACT CONTENT
                title = note.get('name', 'Untitled Project')
                summary = note.get('summary', '')
                created_at = note.get('createdAt', str(datetime.now()))
                
                topic_match = re.search(r'\[MAIN_TOPIC\](.*?)(?=\[|$)', summary, re.DOTALL | re.IGNORECASE)
                main_topic = topic_match.group(1).strip() if topic_match else ""
                checklist_items = extract_items_from_summary(summary)
                
                # FALLBACK EXTRACTION
                if not checklist_items:
                    content = note.get('beautifiedContent', note.get('rawTranscription', ''))
                    sentences = content.replace('\n', '. ').split('. ')
                    keywords = ["need", "must", "should", "todo", "plan"]
                    for s in sentences:
                        if any(k in s.lower() for k in keywords):
                            checklist_items.append(s.strip())

                if checklist_items:
                    project_id = generate_id(title + created_at)
                    checklist_data = [{"text": item, "done": False} for item in checklist_items]
                    
                    current_db['projects'].append({
                        "id": project_id,
                        "notie_id": notie_id,
                        "title": title,
                        "topic": main_topic,
                        "created_at": created_at,
                        "checklist": checklist_data,
                        "archived": False,
                        "user_notes": ""
                    })
                    
                    if 'imported_ids' not in current_db: current_db['imported_ids'] = []
                    current_db['imported_ids'].append(notie_id)
                    new_count += 1
                    file_new_tasks += 1
            
            if file_new_tasks > 0:
                logs.append(f"✅ **{entry.name}**: Success! Imported {file_new_tasks} new projects.")
            else:
                logs.append(f"⚠️ **{entry.name}**: File read, but all Note IDs inside were duplicates.")

            current_db['processed_files'].append(entry.name)
        
        if new_count > 0:
            save_database(current_db)
            st.session_state.db_cache = current_db
            
        return new_count, logs

    except Exception as e:
        return 0, [f"❌ System Error: {str(e)}"]

# --- UI CALLBACKS ---
def toggle_item(project_id, item_index):
    db = st.session_state.db_cache
    for p in db['projects']:
        if p['id'] == project_id:
            p['checklist'][item_index]['done'] = not p['checklist'][item_index]['done']
            break
    save_database(db)
    st.toast("Saved!")

def update_note(project_id):
    new_val = st.session_state[f"n_{project_id}"]
    db = st.session_state.db_cache
    for p in db['projects']:
        if p['id'] == project_id:
            p['user_notes'] = new_val
            break
    save_database(db)
    st.toast("Note saved.")

def archive_proj(project_id, status):
    db = st.session_state.db_cache
    for p in db['projects']:
        if p['id'] == project_id:
            p['archived'] = status
            break
    save_database(db)
    st.toast("Status updated.")
    
# --- MAIN UI ---

st.title("🚀 Notie Project Hub")

if st.session_state.db_cache is None:
    st.session_state.db_cache = load_database()

with st.sidebar:
    st.header("Controls")
    
    # SYNC BUTTON with LOGS
    if st.button("🔄 Check for New Notes", type="primary"):
        with st.spinner("Scanning Dropbox..."):
            count, logs = sync_new_files()
            
            if count > 0:
                st.success(f"Imported {count} new projects!")
            elif len(logs) > 0:
                st.info("Scan complete. See logs below.")
            else:
                st.warning("No files found.")
            
            st.divider()
            st.subheader("📜 Sync Logs")
            for log in logs:
                st.markdown(log)
                    
    st.divider()
    view_mode = st.radio("View:", ["Active Projects", "Archived"])
    hide_completed = st.toggle("Hide completed items")

# --- RENDER ---
db = st.session_state.db_cache
is_archived = (view_mode == "Archived")
visible_projects = [p for p in db['projects'] if p.get('archived', False) == is_archived]

if not visible_projects:
    st.info("No projects visible.")

for project in visible_projects:
    total = len(project['checklist'])
    done = len([x for x in project['checklist'] if x['done']])
    
    icon = "✅" if (total > 0 and total == done) else "📌"
    
    with st.expander(f"{icon} {project['title']} ({done}/{total})", expanded=not is_archived):
        if project['topic']: st.info(project['topic'])
        
        for i, item in enumerate(project['checklist']):
            if hide_completed and item['done']: continue
            c1, c2 = st.columns([0.05, 0.95])
            with c1:
                st.checkbox("Done", item['done'], key=f"{project['id']}_{i}", label_visibility="collapsed", on_change=toggle_item, args=(project['id'], i))
            with c2:
                if item['done']: st.markdown(f"~~{item['text']}~~")
                else: st.write(item['text'])
        
        st.divider()
        c1, c2 = st.columns([3, 1])
        with c1:
            st.text_area("Notes", project['user_notes'], height=70, key=f"n_{project['id']}", on_change=update_note, args=(project['id'],))
        with c2:
            st.write(""); st.write("")
            lbl = "Unarchive" if is_archived else "Archive"
            st.button(lbl, key=f"a_{project['id']}", on_click=archive_proj, args=(project['id'], not is_archived))