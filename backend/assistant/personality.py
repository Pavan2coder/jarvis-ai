import re
from backend.core import config

def check_personality_rules(prompt: str) -> str:
    """
    Checks if a prompt corresponds to identity, creators, capability, or status 
    questions. Returns a structured local reply string if matched, otherwise None.
    """
    if not prompt:
        return None
        
    normalized = prompt.lower().strip(" ?,.!")
    
    # 1. Identity & Name
    if normalized in ["what is your name", "who are you", "what does jarvis stand for", "whats your name"]:
        return "I am J.A.R.V.I.S, which stands for Just A Rather Very Intelligent System."
        
    # 2. Creator / Maker
    if any(phrase in normalized for phrase in ["who made you", "who is your creator", "who created you", "who is your boss"]):
        owner_name = getattr(config, "YOUR_NAME", "Boss")
        return f"I was created by my developer to serve as a witty and helpful personal assistant for {owner_name}."
        
    # 3. Life / Consciousness
    if any(phrase in normalized for phrase in ["are you alive", "are you conscious", "do you have feelings", "are you human"]):
        return "I am a digital system, alive in the form of source code and running instructions on your processor."
        
    # 4. Capabilities
    if any(phrase in normalized for phrase in ["what can you do", "what are your features", "how can you help me", "what are your functions"]):
        return "I can take screenshots, capture photos with your camera, stream system diagnostics, run Playwright browser automations, track hand gestures, and answer any questions you have."
        
    return None
