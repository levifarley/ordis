from typing import Callable, List, Dict, Any, Tuple
import logging

logger = logging.getLogger("ordis.hooks")

# Type definitions for hook functions
PrePromptHook = Callable[[str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]
PostResponseHook = Callable[[str, str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]

_pre_prompt_hooks: List[PrePromptHook] = []
_post_response_hooks: List[PostResponseHook] = []

def register_pre_prompt_hook(hook: PrePromptHook):
    """Registers a function to run before RAG vector search & LLM inference."""
    _pre_prompt_hooks.append(hook)
    logger.info(f"Registered pre-prompt hook: {hook.__name__}")

def register_post_response_hook(hook: PostResponseHook):
    """Registers a function to run after LLM generation."""
    _post_response_hooks.append(hook)
    logger.info(f"Registered post-response hook: {hook.__name__}")

def execute_pre_prompt_hooks(query: str, context: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Runs all registered pre-prompt hooks sequentially."""
    current_query = query
    current_context = context.copy()
    
    for hook in _pre_prompt_hooks:
        try:
            current_query, current_context = hook(current_query, current_context)
        except Exception as e:
            logger.error(f"Error executing pre-prompt hook '{hook.__name__}': {e}")
            
    return current_query, current_context

def execute_post_response_hooks(query: str, response: str, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Runs all registered post-response hooks sequentially."""
    current_response = response
    current_payload = payload.copy()
    
    for hook in _post_response_hooks:
        try:
            current_response, current_payload = hook(query, current_response, current_payload)
        except Exception as e:
            logger.error(f"Error executing post-response hook '{hook.__name__}': {e}")
            
    return current_response, current_payload

# Default builtin hooks
def default_input_sanitizer_hook(query: str, context: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Sanitizes user prompt by stripping HTML tags."""
    import re
    clean_query = re.sub(r'<[^>]*>', '', query).strip()
    return clean_query, context

def deduplicate_lines_hook(query: str, response: str, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Strips duplicate consecutive paragraphs/lines from the response as a modular output safety net."""
    if not response:
        return response, payload
        
    paragraphs = response.split("\n\n")
    seen_paras = set()
    unique_paras = []
    for p in paragraphs:
        normalized = p.strip()
        if normalized and normalized not in seen_paras:
            seen_paras.add(normalized)
            unique_paras.append(p)
    cleaned_response = "\n\n".join(unique_paras)
    return cleaned_response, payload

register_pre_prompt_hook(default_input_sanitizer_hook)
register_post_response_hook(deduplicate_lines_hook)
