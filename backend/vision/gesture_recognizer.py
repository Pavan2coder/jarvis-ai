import math

def get_distance(lm1, lm2) -> float:
    """Calculates normalized Euclidean distance between two landmark objects."""
    return math.hypot(lm1.x - lm2.x, lm1.y - lm2.y)

def get_finger_states(landmarks) -> list:
    """
    Evaluates finger states and returns open/closed booleans.
    List format: [thumb, index, middle, ring, pinky]
    Uses orientation-invariant distance-to-wrist ratios for high reliability.
    """
    states = [False] * 5
    
    wrist = landmarks[0]
    
    # 1. Index, Middle, Ring, Pinky: open if distance from tip to wrist
    # is greater than distance from PIP joint to wrist.
    states[1] = get_distance(landmarks[8], wrist) > get_distance(landmarks[6], wrist)
    states[2] = get_distance(landmarks[12], wrist) > get_distance(landmarks[10], wrist)
    states[3] = get_distance(landmarks[16], wrist) > get_distance(landmarks[14], wrist)
    states[4] = get_distance(landmarks[20], wrist) > get_distance(landmarks[18], wrist)
    
    # 2. Thumb: compare distance between thumb tip (4) and index knuckle (5)
    # to knuckle span (5 to 17) to maintain hand-agnostic check.
    d_thumb_index = get_distance(landmarks[4], landmarks[5])
    d_span = max(0.001, get_distance(landmarks[5], landmarks[17]))
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
    d_span = max(0.001, get_distance(landmarks[5], landmarks[17]))
    
    # Check index pinch (thumb tip to index tip)
    d_pinch_index = get_distance(landmarks[4], landmarks[8])
    d_pinch_index_norm = d_pinch_index / d_span
    is_index_pinched = d_pinch_index_norm < 0.28
    
    # A. Open Palm (🖐️) -> Activate Jarvis / Swipe / Screenshot
    if all(states) or (states[1] and states[2] and states[3] and states[4]):
        return "Open Palm", "Activate Jarvis"
        
    # B. Fist (✊) -> Click/Drag
    if not any(states):
        return "Fist", "Click/Drag"
        
    # C. Thumbs Up (👍) -> Play/Pause Music
    if states[0] and not any(states[1:]):
        return "Thumbs Up", "Play/Pause"
        
    # D. Peace Sign (✌️) -> Scroll Mode
    if states[1] and states[2] and not states[3] and not states[4]:
        d_tips = get_distance(landmarks[8], landmarks[12])
        d_tips_norm = d_tips / d_span
        if d_tips_norm > 0.45:
            return "Peace Sign", "None"
        else:
            return "Peace Sign", "Scroll"
            
    # E. Volume Gesture (Ring + Pinky up, Index + Middle down)
    if states[3] and states[4] and not states[1] and not states[2]:
        return "Volume Gesture", "Adjusting Volume"

    # F. Pinky Tap / Pinky Up
    if states[4] and not states[1] and not states[2] and not states[3]:
        return "Pinky Tap", "RIGHT CLICK"

    # G. Ring Tap / Ring Up
    if states[3] and not states[1] and not states[2] and not states[4]:
        return "Ring Tap", "MIDDLE CLICK"

    # H. Index Pinch
    if is_index_pinched:
        return "Index Pinch", "LEFT CLICK"

    # I. Virtual Mouse Mode (Index finger pointing)
    if states[1]:
        d_pinch_middle = get_distance(landmarks[4], landmarks[12])
        d_pinch_middle_norm = d_pinch_middle / d_span
        if d_pinch_middle_norm < 0.28:
            return "Middle Pinch", "Mute"
        else:
            return "Index Point", "Hover/Move Mouse"
            
    return "None", "None"

