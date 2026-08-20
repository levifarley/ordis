import telemetry_optout
import os
import sys
import time
import logging
import base64
from typing import Generator, List
import streamlit as st
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("ordis.frontend")

# Backend Service Configuration
BACKEND_URL = os.getenv("BACKEND_URL", os.getenv("BACKEND_API_URL", "http://localhost:8000"))
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "operator")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "cephalon")
PROMPT_CHARACTER_LIMIT = int(os.getenv("PROMPT_CHARACTER_LIMIT", "250"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "10"))

# Page Setup
st.set_page_config(
    page_title="ORDIS",
    page_icon="⚔️",
    layout="centered"
)

# Dark Theme styling via custom CSS injection
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"], [data-testid="stHeader"], [data-testid="stBottom"], [data-testid="stBottom"] *, [data-testid="stBottomBlockContainer"], [data-testid="stBottomBlockContainer"] *, div[class*="stBottom"], div[class*="stBottom"] *, footer, .stApp, [data-testid="stSidebar"] {
        background-color: #04050a !important;
        background: #04050a !important;
        color: #e0e6ed;
    }
    [data-testid="stChatMessage"] {
        background-color: #04050a !important;
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
        background-color: #04050a !important;
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
    .stChatInputContainer textarea,
    .stChatInputContainer textarea:focus,
    [data-testid="stChatInputTextArea"],
    [data-testid="stChatInputTextArea"]:focus {
        background-color: #04050a !important;
        color: #e0e6ed !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }
    [data-testid="stChatMessageAvatarAssistant"], 
    [data-testid="stChatMessageAvatarUser"], 
    [data-testid="chatAvatar"] {
        display: none !important;
    }
    .stChatMessage:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
        color: #2dd4bf !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def get_base64_logo() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "assets", "ordis_logo.png"),
        os.path.join(os.path.dirname(base_dir), "ordis_logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    return ""

logo_base64 = get_base64_logo()
if logo_base64:
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; margin-top: 15px; margin-bottom: 25px;">
            <img src="data:image/png;base64,{logo_base64}" style="width: 500px; max-width: 100%; border-radius: 8px;"/>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_copy_button(text: str, element_id: str):
    escaped_text = text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace('\n', '\\n').replace('\r', '\\r')
    html_code = f"""
    <style>
    body {{ margin: 0; padding: 0; overflow: hidden; background-color: transparent; }}
    .container {{ display: flex; justify-content: flex-end; align-items: center; height: 20px; padding-right: 4px; }}
    button {{ background-color: transparent; color: rgba(255, 255, 255, 0.45); border: none; padding: 2px; cursor: pointer; transition: color 0.15s ease-in-out; outline: none; display: flex; align-items: center; height: 20px; }}
    button:hover {{ color: rgba(255, 255, 255, 0.85); }}
    </style>
    <div class="container">
        <textarea id="t-{element_id}" style="position: absolute; left: -9999px;">{escaped_text}</textarea>
        <button onclick="doCopy('{element_id}')" id="b-{element_id}">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path></svg>
        </button>
    </div>
    <script>
    function doCopy(id) {{
        var copyText = document.getElementById('t-' + id);
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        document.execCommand('copy');
        var btn = document.getElementById('b-' + id);
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>';
        setTimeout(function() {{
            btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path></svg>';
        }}, 2000);
    }}
    </script>
    """
    st.components.v1.html(html_code, height=20)

def get_target_backend_urls() -> List[str]:
    candidates = []
    if BACKEND_URL:
        candidates.append(BACKEND_URL)
    for fallback in ["http://backend:8000", "http://127.0.0.1:8000", "http://localhost:8000"]:
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates

# OAuth Authentication Handler
def fetch_access_token(username: str = DEFAULT_USERNAME, password: str = DEFAULT_PASSWORD) -> str:
    for base_url in get_target_backend_urls():
        try:
            url = f"{base_url}/api/auth/token"
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, data={"username": username, "password": password})
                if res.status_code == 200:
                    data = res.json()
                    token = data.get("access_token", "")
                    if token:
                        return token
                else:
                    logger.error(f"Authentication failed at {base_url}: {res.status_code} {res.text}")
        except Exception as e:
            logger.warning(f"Could not connect to backend auth at {base_url}: {e}")
    return ""

if "access_token" not in st.session_state or not st.session_state.access_token:
    st.session_state.access_token = fetch_access_token()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Operator, how may I assist your Warframe queries today?"}
    ]

if "last_prompt_time" not in st.session_state:
    st.session_state.last_prompt_time = 0.0

# Render Session Messages
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_copy_button(message["content"], f"msg-{idx}")

# Handle User Prompt
user_prompt = st.chat_input(
    placeholder="Ask about Warframe weapons, builds, or drops...",
    max_chars=PROMPT_CHARACTER_LIMIT
)

if user_prompt:
    current_time = time.time()
    elapsed = current_time - st.session_state.last_prompt_time
    
    if elapsed < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - elapsed)
        st.error(f"⏳ Security cooldown active. Please wait {remaining} second(s) before querying again.")
    elif len(user_prompt) > PROMPT_CHARACTER_LIMIT:
        st.error(f"Your query exceeds the character limit of {PROMPT_CHARACTER_LIMIT} characters.")
    else:
        st.session_state.last_prompt_time = current_time

        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)
            render_copy_button(user_prompt, f"msg-{len(st.session_state.messages)-1}")

        with st.chat_message("assistant"):
            def stream_from_backend() -> Generator[str, None, None]:
                token = st.session_state.get("access_token")
                if not token:
                    token = fetch_access_token()
                    st.session_state.access_token = token

                if not token:
                    yield "Cephalon Ordis is initializing systems, please wait a minute or two and refresh the page."
                    return

                payload = {
                    "prompt": user_prompt,
                    "chat_history": st.session_state.messages[:-1]
                }
                
                last_exception = None
                for base_url in get_target_backend_urls():
                    try:
                        headers = {"Authorization": f"Bearer {token}"}
                        url = f"{base_url}/api/chat/stream"
                        with httpx.Client(timeout=60.0) as client:
                            with client.stream("POST", url, headers=headers, json=payload) as response:
                                if response.status_code == 200:
                                    has_content = False
                                    for line in response.iter_raw():
                                        if line:
                                            has_content = True
                                            yield line.decode("utf-8")
                                    if has_content:
                                        return
                                elif response.status_code == 401:
                                    token = fetch_access_token()
                                    st.session_state.access_token = token
                                    if token:
                                        headers = {"Authorization": f"Bearer {token}"}
                                        with client.stream("POST", url, headers=headers, json=payload) as retry_res:
                                            if retry_res.status_code == 200:
                                                for line in retry_res.iter_raw():
                                                    if line:
                                                        yield line.decode("utf-8")
                                                return
                    except Exception as e:
                        last_exception = e
                        logger.warning(f"Failed streaming from backend at {base_url}: {e}")

                logger.error(f"Backend streaming error: {last_exception}")
                yield "Cephalon Ordis is initializing systems, please wait a minute or two and refresh the page."

            with st.spinner("Searching Codex databases..."):
                response_text = st.write_stream(stream_from_backend())
            
            render_copy_button(response_text, f"msg-{len(st.session_state.messages)}")

        st.session_state.messages.append({"role": "assistant", "content": response_text})
