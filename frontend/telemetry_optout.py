"""
Streamlit Telemetry Opt-Out & Metric Stripper
Ensures all Streamlit telemetry, analytics, and usage gathering features are disabled.
"""
import os
import sys

# Set environment variables to turn off Streamlit usage statistics and telemetry
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_TELEMETRY_OPTOUT"] = "1"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"

# Monkey-patch or disable streamlit telemetry functions if already imported
try:
    import streamlit.telemetry as telemetry
    
    def nop_func(*args, **kwargs):
        pass

    if hasattr(telemetry, "track"):
        telemetry.track = nop_func
    if hasattr(telemetry, "send"):
        telemetry.send = nop_func
except ImportError:
    pass
