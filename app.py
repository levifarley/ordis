import os
import sys
import time
import logging
import threading
import base64
from datetime import datetime, timezone
import streamlit as st
import config

# Configure basic logging to terminal stdout
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Import your existing RAG engine logic
try:
    from rag_engine import RAGEngine
    from firestore_db import get_firestore_client
except ImportError:
    st.error("Could not import dependencies. Ensure rag_engine.py and firestore_db.py exist in the directory.")
    st.stop()

# Set up Streamlit page layout
st.set_page_config(
    page_title="ORDIS",
    page_icon="⚔️",
    layout="centered"
)

# Dark Theme styling via custom injection
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"], [data-testid="stHeader"], [data-testid="stBottom"], [data-testid="stBottomBlockContainer"], .stApp, [data-testid="stSidebar"], .st-emotion-cache-hzygls.e15ve43o3 {
        background-color: #010207 !important;
        color: #e0e6ed;
    }
    [data-testid="stChatMessage"] {
        background-color: #010207 !important;
        border: 1px solid rgba(45, 212, 191, 0.15) !important;
        border-radius: 8px !important;
        padding: 16px 20px !important;
    }
    .stButton>button {
        background-color: #111827;
        color: #e0e6ed;
        border: 1px solid #374151;
    }
    .stChatInputContainer,
    div[data-testid="stChatInput"] > div {
        border-color: rgba(45, 212, 191, 0.25) !important;
        background-color: #010207 !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    .stChatInputContainer:focus-within,
    div[data-testid="stChatInput"] > div:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 1px #10b981 !important;
    }
    .stChatInputContainer.char-limit-reached,
    .stChatInputContainer.char-limit-reached:focus-within,
    div[data-testid="stChatInput"] > div.char-limit-reached,
    div[data-testid="stChatInput"] > div.char-limit-reached:focus-within {
        border-color: #ef4444 !important;
        box-shadow: 0 0 0 1px #ef4444 !important;
    }
    .stChatInputContainer:has(textarea:disabled),
    div[data-testid="stChatInput"] > div:has(textarea:disabled) {
        border-color: #ef4444 !important;
        box-shadow: none !important;
    }
    .stChatInputContainer textarea,
    .stChatInputContainer textarea:focus,
    [data-testid="stChatInputTextArea"],
    [data-testid="stChatInputTextArea"]:focus {
        background-color: #010207 !important;
        color: #e0e6ed !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }
    div[data-testid="stChatInput"],
    div[data-testid="stChatInput"] > div {
        outline: none !important;
    }
    /* Hide all chat avatars (robot/user icons) */
    [data-testid="stChatMessageAvatarAssistant"], 
    [data-testid="stChatMessageAvatarUser"], 
    [data-testid="chatAvatar"] {
        display: none !important;
    }
    /* Style Assistant (Response) Messages with Bright Teal Text */
    .stChatMessage:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
        color: #2dd4bf !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Load cropped ordis logo and encode to base64
def get_base64_logo():
    logo_path = "/projects/ordis/ordis_logo.png"
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                data = f.read()
                return base64.b64encode(data).decode("utf-8")
        except Exception:
            pass
    return ""

logo_base64 = get_base64_logo()

# Logo styling for Ordis (using the custom holographic Cephalon core logo)
if logo_base64:
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; margin-top: 15px; margin-bottom: 25px;">
            <img src="data:image/png;base64,{logo_base64}" style="width: 500px; max-width: 100%; border-radius: 8px;"/>
        </div>
        """,
        unsafe_allow_html=True
    )

# Helper to render a copy-to-clipboard button
def render_copy_button(text: str, element_id: str):
    escaped_text = text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace('\n', '\\n').replace('\r', '\\r')
    html_code = f"""
    <div style="display: flex; justify-content: flex-end; margin-top: -15px; margin-bottom: 2px;">
        <textarea id="t-{element_id}" style="position: absolute; left: -9999px;">{escaped_text}</textarea>
        <button onclick="doCopy('{element_id}')" id="b-{element_id}" style="
            background-color: transparent;
            color: rgba(255, 255, 255, 0.45);
            border: none;
            padding: 4px;
            cursor: pointer;
            transition: color 0.15s ease-in-out;
            outline: none;
            display: flex;
            align-items: center;
            font-size: 11px;
            font-family: inherit;
        " onmouseover="this.style.color='rgba(255,255,255,0.85)';" onmouseout="this.style.color='rgba(255,255,255,0.45)';">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
        </button>
    </div>
    <script>
    function doCopy(id) {{
        var copyText = document.getElementById('t-' + id);
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        document.execCommand('copy');
        var btn = document.getElementById('b-' + id);
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
        setTimeout(function() {{
            btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';
        }}, 2000);
    }}
    </script>
    """
    st.components.v1.html(html_code, height=28)

# -------------------------------------------------------------------
# 1. CACHED INITIALIZATION & RATE LIMITS
# -------------------------------------------------------------------
@st.cache_resource
def get_rag_engine():
    """
    Initializes and caches the RAG Engine client connection to GCP/Firestore.
    """
    project_id = os.environ.get("GCP_PROJECT", "warframe-503817")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    return RAGEngine(project_id=project_id, location=location)

rag_engine = get_rag_engine()

# Helper to check if the daily usage limit is already reached
def is_usage_limit_reached() -> bool:
    try:
        db = get_firestore_client()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc_ref = db.collection("telemetry").document("usage_stats")
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("last_reset") == today_str:
                return data.get("query_count", 0) >= config.MAX_DAILY_QUERIES
    except Exception:
        # Fail-safe to False if database is initializing
        pass
    return False

limit_reached = is_usage_limit_reached()

if limit_reached:
    st.warning("⚠️ Codex AI is sleeping. The daily public query limit has been reached to keep this app free. Please check back tomorrow!")

# Initialize Chat Session History in Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Operator, how may I assist your Warframe queries today?"}
    ]

if "last_prompt_time" not in st.session_state:
    st.session_state.last_prompt_time = 0.0

# Render existing conversation history
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_copy_button(message["content"], f"msg-{idx}")

# -------------------------------------------------------------------
# 2. PROMPT HANDLING & ASYNC TELEMETRY
# -------------------------------------------------------------------
user_prompt = st.chat_input(
    placeholder="Ask about Warframe weapons, builds, or drops..." if not limit_reached else "Daily limit reached. Chat input locked.",
    max_chars=config.PROMPT_CHARACTER_LIMIT,
    disabled=limit_reached
)

if user_prompt:
    current_time = time.time()
    elapsed = current_time - st.session_state.last_prompt_time
    
    # A. Cooldown Guard Check
    if elapsed < config.COOLDOWN_SECONDS:
        remaining = int(config.COOLDOWN_SECONDS - elapsed)
        st.error(f"⏳ Security cooldown active. Please wait {remaining} second(s) before querying again.")
    # B. Input Length Check
    elif len(user_prompt) > config.PROMPT_CHARACTER_LIMIT:
        st.error(f"Your query exceeds the character limit of {config.PROMPT_CHARACTER_LIMIT} characters.")
    else:
        # Update rate limiting timestamp
        st.session_state.last_prompt_time = current_time
        
        # Print explicitly to WSL2 terminal with immediate buffer flush
        print(f"\n[LOCAL LOG] User Prompt Received: {user_prompt}", flush=True)

        # Append & render user message immediately
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)
            render_copy_button(user_prompt, f"msg-{len(st.session_state.messages)-1}")

        # Prepare Assistant message box
        with st.chat_message("assistant"):
            # Stream response directly to UI
            def stream_generator():
                # Generate response stream from RAG engine with chat history context
                chat_history = st.session_state.messages[:-1]
                print(f"[LOCAL LOG DEBUG] st.session_state.messages size: {len(st.session_state.messages)}", flush=True)
                print(f"[LOCAL LOG DEBUG] chat_history list: {chat_history}", flush=True)
                response_stream, telemetry_payload = rag_engine.generate_response_stream(user_prompt, chat_history)
                
                full_response_text = ""
                for chunk in response_stream:
                    if hasattr(chunk, 'text'):
                        chunk_text = chunk.text or ""
                    else:
                        chunk_text = str(chunk)
                        
                    if chunk_text.startswith("LIMIT_EXCEEDED:"):
                        chunk_text = chunk_text.replace("LIMIT_EXCEEDED:", "").strip()
                        st.session_state["limit_exceeded_triggered"] = True
                    full_response_text += chunk_text
                    yield chunk_text

                # Cache final full response text for telemetry logging
                st.session_state["last_telemetry_payload"] = telemetry_payload
                st.session_state["last_response_text"] = full_response_text

            # Use Streamlit's built-in stream renderer inside a clean thinking spinner
            with st.spinner("Searching Codex databases..."):
                response_text = st.write_stream(stream_generator())
            
            # Render copy button immediately inside the assistant message block
            render_copy_button(response_text, f"msg-{len(st.session_state.messages)}")

        # Save complete assistant response to UI session history
        st.session_state.messages.append({"role": "assistant", "content": response_text})

        # C. Handle Visual Lock Trigger
        if st.session_state.get("limit_exceeded_triggered"):
            st.session_state["limit_exceeded_triggered"] = False
            st.rerun()

        # -------------------------------------------------------------------
        # 3. NON-BLOCKING BACKGROUND TELEMETRY LOGGING
        # -------------------------------------------------------------------
        def log_telemetry_async(prompt, response, payload):
            """
            Executes Vertex AI Experiment/Tensorboard telemetry off the main thread.
            Prevents GCP network latency from blocking UI rendering.
            """
            try:
                rag_engine.log_telemetry_to_vertex(
                    prompt=prompt,
                    response=response,
                    payload=payload
                )
                print("[LOCAL LOG] Telemetry successfully dispatched to Vertex AI Experiments.", flush=True)
            except Exception as e:
                print(f"[LOCAL LOG ERROR] Asynchronous telemetry logging failed: {e}", flush=True)

        # Launch telemetry logging in a background thread
        telemetry_payload = st.session_state.get("last_telemetry_payload", {})
        threading.Thread(
            target=log_telemetry_async,
            args=(user_prompt, response_text, telemetry_payload),
            daemon=True
        ).start()

# Inject a JavaScript helper to insert a copy button beside the chat input submit button
input_copy_js = """
<script>
function injectInputCopyButton() {
    var chatInputContainer = window.parent.document.querySelector('div[data-testid="stChatInput"]');
    if (chatInputContainer) {
        // 1. Inject Copy Button if missing
        if (!window.parent.document.getElementById('custom-input-copy-btn')) {
            var submitBtn = chatInputContainer.querySelector('button');
            if (submitBtn) {
                var copyBtn = window.parent.document.createElement('button');
                copyBtn.id = 'custom-input-copy-btn';
                copyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';
                copyBtn.style.backgroundColor = 'transparent';
                copyBtn.style.color = 'rgba(255, 255, 255, 0.45)';
                copyBtn.style.border = 'none';
                copyBtn.style.padding = '8px';
                copyBtn.style.cursor = 'pointer';
                copyBtn.style.outline = 'none';
                copyBtn.style.marginRight = '4px';
                copyBtn.style.display = 'flex';
                copyBtn.style.alignItems = 'center';
                copyBtn.style.transition = 'color 0.15s';
                
                copyBtn.onmouseover = function() { this.style.color = 'rgba(255, 255, 255, 0.85)'; };
                copyBtn.onmouseout = function() { this.style.color = 'rgba(255, 255, 255, 0.45)'; };
                
                copyBtn.onclick = function(e) {
                    e.preventDefault();
                    var textarea = chatInputContainer.querySelector('textarea');
                    if (textarea) {
                        navigator.clipboard.writeText(textarea.value).then(function() {
                            copyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
                            setTimeout(function() {
                                copyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';
                            }, 2000);
                        });
                    }
                };
                submitBtn.parentNode.insertBefore(copyBtn, submitBtn);
            }
        }
        
        // 2. Validate Limit & Cooldown to Highlight Border Red/Green
        var textarea = chatInputContainer.querySelector('textarea');
        if (textarea) {
            var maxChars = 250;
            var checkLimit = function() {
                var hasCooldownOrLimit = false;
                var alerts = window.parent.document.querySelectorAll('[data-testid="stNotification"]');
                for (var i = 0; i < alerts.length; i++) {
                    var txt = alerts[i].innerText.toLowerCase();
                    if (txt.indexOf('cooldown') !== -1 || txt.indexOf('limit') !== -1 || txt.indexOf('exceeds') !== -1) {
                        hasCooldownOrLimit = true;
                        break;
                    }
                }
                if (textarea.value.length >= maxChars || hasCooldownOrLimit || textarea.disabled) {
                    chatInputContainer.classList.add('char-limit-reached');
                } else {
                    chatInputContainer.classList.remove('char-limit-reached');
                }
            };
            
            if (!textarea.dataset.limitBound) {
                textarea.addEventListener('input', checkLimit);
                textarea.addEventListener('focus', checkLimit);
                textarea.dataset.limitBound = "true";
            }
            checkLimit();
        }
    }
}
setTimeout(injectInputCopyButton, 100);
setInterval(injectInputCopyButton, 1000);
</script>
"""
st.components.v1.html(input_copy_js, height=0)