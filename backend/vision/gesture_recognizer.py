import math

def get_distance(lm1, lm2) -> float:
    """Calculates normalized Euclidean distance between two landmark objects."""
    return math.hypot(lm1.x - lm2.x, lm1.y - lm2.y)

def get_finger_states(landmarks) -> list:
    """
    Evaluates finger states and returns open/closed booleans.
    List format: [thumb, index, middle, ring, pinky]
    """
    states = [False] * 5
    
    # 1. Index, Middle, Ring, Pinky: open if tip y < pip y
    states[1] = landmarks[8].y < landmarks[6].y
    states[2] = landmarks[12].y < landmarks[10].y
    states[3] = landmarks[16].y < landmarks[14].y
    states[4] = landmarks[20].y < landmarks[18].y
    
    # 2. Thumb: compare distance between thumb tip (4) and index knuckle (5)
    # to knuckle span (5 to 17) to maintain hand-agnostic check.
    d_thumb_index = get_distance(landmarks[4], landmarks[5])
    d_span = get_distance(landmarks[5], landmarks[17])
    states[0] = d_thumb_index > d_span * 0.65
    
    return states

def classify_gesture(landmarks) -> tuple:
    """
    Parses normalized hand landmarks to identify the corresponding 
    active gesture and system action.
    
    Returns:
        tuple: (gesture_name, action_name)
    """
    if not landmarks:
        return "None", "None"
        
    states = get_finger_states(landmarks)
    
    # A. Open Palm (🖐️) -> Activate Jarvis
    if all(states):
        return "Open Palm", "Activate Jarvis"
        
    # B. Fist (✊) -> Toggle Mute
    if not any(states):
        return "Fist", "Mute"
        
    # C. Thumbs Up (👍) -> Play/Pause Music
    if states[0] and not any(states[1:]):
        return "Thumbs Up", "Play/Pause"
        
    # D. Peace Sign (✌️) -> Scroll Mode / Hover
    if states[1] and states[2] and not states[3] and not states[4]:
        d_tips = get_distance(landmarks[8], landmarks[12])
        if d_tips > 0.055:
            # Spread -> hover / standard peace
            return "Peace Sign", "None"
        else:
            # Close -> Scroll Mode
            return "Peace Sign", "Scroll"
            
    # E. Virtual Mouse Mode (Index finger pointing or pinching)
    # Triggered if index is open and we aren't in peace sign/palm.
    if states[1]:
        d_pinch = get_distance(landmarks[4], landmarks[8])
        if d_pinch < 0.035:
            return "Index Pinch", "Click/Drag"
        else:
            return "Index Point", "Hover/Move Mouse"
            
    return "None", "None"
