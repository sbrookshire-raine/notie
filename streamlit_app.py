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
    st.error("❌ Secrets missing. Check .streamlit/secrets.toml")
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

# --- CORE FUNCTIONS ---

def load_database():
    """Download DB from Dropbox."""
    try:
        metadata, response = dbx.files_download(DATA_FILENAME)
        return json.loads(response.content.decode('utf-8'))
    except Exception:
        return {"projects": [], "imported_ids": [], "processed_files": []}

def save_database(data):
    """Upload DB to Dropbox."""
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
    if not summary_text:
        return items
    match = re.search(r'\[ITEMS\](.*?)(?=\[|$)', summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        lines = block.split('\n')
        for line in lines:
            clean_line = re.sub(r'^[-*•\d\.]+\s*', '', line).strip()
            if clean_line:
                items.append(clean_line)
    return items

# --- CALLBACKS (The Magic Part) ---
# These run immediately when you interact with a widget

def toggle_item_callback(project_id, item_index):
    """Updates the specific item and saves immediately."""
    db = st.session_state.db_cache
    
    # Find project
    for p in db['projects']:
        if p['id'] == project_id:
            # Toggle status
            current_status = p['checklist'][item_index]['done']
            p['checklist'][item_index]['done'] = not current_status
            break
            
    # Save to cloud
    save_database(db)
    st.toast("✅ Saved change!")

def update_notes_callback(project_id):
    """Updates the project notes."""
    # We get the new text from the specific text_area key
    new_text = st.session_state[f"n_{project_id}"]
    db = st.session_state.db_cache
    
    for p in db['projects']:
        if p['id'] == project_id:
            p['user_notes'] = new_text
            break
            
    save_database(db)
    st.toast("📝 Notes saved!")

def archive_project_callback(project_id, archive_status):
    """Archives or Unarchives a project."""
    db = st.session_state.db_cache
    for p in db['projects']:
        if p['id'] == project_id:
            p['archived'] = archive_status
            break
    save_database(db)
    st.toast("📦 Project status updated!")

def sync_new_files():
    """Runs the heavy file scanning logic."""
    current_db = st.session_state.db_cache
    new_count = 0
    
    try:
        result = dbx.files_list_folder("")
        
        for entry in result.entries:
            if entry.name.endswith(".json") and "db" not in entry.name:
                if entry.name not in current_db['processed_files']:
                    
                    md, res = dbx.files_download(entry.path_lower)
                    try:
                        data = json.loads(res.content.decode('utf-8'))
                    except:
                        continue
                    
                    notes = data.get("notes", data) if isinstance(data, dict) else data
                    if isinstance(notes, dict): notes = [notes]

                    for note in notes:
                        notie_id = note.get('id')
                        if notie_id in current_db.get('imported_ids', []):
                            continue

                        title = note.get('name', 'Untitled Project')
                        summary = note.get('summary', '')
                        created_at = note.get('createdAt', str(datetime.now()))
                        
                        topic_match = re.search(r'\[MAIN_TOPIC\](.*?)(?=\[|$)', summary, re.DOTALL | re.IGNORECASE)
                        main_topic = topic_match.group(1).strip() if topic_match else ""
                        checklist_items = extract_items_from_summary(summary)
                        
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
                    
                    current_db['processed_files'].append(entry.name)
        
        if new_count > 0:
            save_database(current_db)
            return new_count
        return 0

    except Exception as e:
        st.error(f"Scan error: {e}")
        return 0

# --- UI LAYOUT ---

st.title("🚀 Notie Project Hub")

# --- INITIAL LOAD ---
if st.session_state.db_cache is None:
    with st.spinner("Connecting..."):
        st.session_state.db_cache = load_database()

# --- SIDEBAR ---
with st.sidebar:
    st.header("Controls")
    
    if st.button("🔄 Check for New Notes", type="primary"):
        with st.spinner("Scanning Dropbox..."):
            count = sync_new_files()
            if count > 0:
                st.success(f"Found {count} new projects!")
                st.rerun()
            else:
                st.info("No new notes found.")

    st.divider()
    view_mode = st.radio("View:", ["Active Projects", "Archived"])
    hide_completed = st.toggle("Hide completed items")

# --- RENDER CARDS ---

db = st.session_state.db_cache
is_archived_view = (view_mode == "Archived")
projects_to_show = [p for p in db['projects'] if p.get('archived', False) == is_archived_view]

if not projects_to_show:
    st.info("No projects here. Import some from your phone!")

for project in projects_to_show:
    
    total_items = len(project['checklist'])
    done_items = len([i for i in project['checklist'] if i['done']])
    
    icon = "📌"
    if done_items == total_items and total_items > 0:
        icon = "✅"
    
    with st.expander(f"{icon} {project['title']} ({done_items}/{total_items})", expanded=not is_archived_view):
        
        if project['topic']:
            st.info(project['topic'])
            
        for i, item in enumerate(project['checklist']):
            if hide_completed and item['done']:
                continue
                
            col1, col2 = st.columns([0.05, 0.95])
            with col1:
                # CHECKBOX WITH CALLBACK
                # Notice: on_change calls the function automatically when clicked
                st.checkbox(
                    "Done", 
                    value=item['done'], 
                    key=f"{project['id']}_{i}", 
                    label_visibility="collapsed",
                    on_change=toggle_item_callback,
                    args=(project['id'], i)
                )
            
            with col2:
                if item['done']:
                    st.markdown(f"<span style='color:grey; text-decoration:line-through'>{item['text']}</span>", unsafe_allow_html=True)
                else:
                    st.write(item['text'])
        
        st.divider()
        
        c1, c2 = st.columns([3, 1])
        with c1:
            # TEXT AREA WITH CALLBACK
            st.text_area(
                "Notes", 
                value=project['user_notes'], 
                height=70, 
                key=f"n_{project['id']}",
                on_change=update_notes_callback,
                args=(project['id'],)
            )
        
        with c2:
            st.write("") 
            st.write("") 
            # BUTTONS WITH CALLBACKS
            if not is_archived_view:
                st.button(
                    "Archive", 
                    key=f"arc_{project['id']}",
                    on_click=archive_project_callback,
                    args=(project['id'], True)
                )
            else:
                st.button(
                    "Unarchive", 
                    key=f"unarc_{project['id']}",
                    on_click=archive_project_callback,
                    args=(project['id'], False)
                )