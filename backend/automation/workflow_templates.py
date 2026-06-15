DEFAULT_TEMPLATES = {
    "coding_setup": {
        "name": "Coding Setup",
        "description": "Prepares development directories, editors, browser documentation, and sets vision control to Work Mode.",
        "execution": "sequential",
        "steps": [
            {
                "action": "speak",
                "target": "Initializing your programming workspace, Boss."
            },
            {
                "execution": "parallel",
                "steps": [
                    {
                        "action": "open_folder",
                        "target": "projects"
                    },
                    {
                        "action": "launch_app",
                        "target": "chrome"
                    },
                    {
                        "action": "browser_search",       
                        "engine": "google",
                        "query": "python developer documentation"
                    }
                ]
            },
            {
                "action": "gesture_profile",
                "target": "work"
            },
            {
                "action": "speak",
                "target": "Coding setup is fully prepared. Let's write some code!"
            }
        ]
    },
    
    "study_mode": {
        "name": "Study Mode",
        "description": "Mutes distractions, turns down volume, loads study beats on YouTube, launches music, and activates Work Mode.",
        "execution": "sequential",
        "steps": [
            {
                "action": "speak",
                "target": "Preparing your study session. Initializing silent focus."
            },
            {
                "execution": "parallel",
                "steps": [
                    {
                        "action": "system_control",
                        "control_type": "volume",
                        "target": 25
                    },
                    {
                        "action": "browser_search",
                        "engine": "youtube",
                        "query": "lofi hip hop focus beats for studying"
                    }
                ]
            },
            {
                "action": "gesture_profile",
                "target": "work"
            },
            {
                "action": "speak",
                "target": "Focus session activated. Let's study."
            }
        ]
    },
    
    "meeting_mode": {
        "name": "Meeting Mode",
        "description": "Prepares presenter display brightness, sets volume levels, opens calendar, and activates Presentation Mode.",
        "execution": "sequential",
        "steps": [
            {
                "action": "speak",
                "target": "Setting up for your meeting. Adjusting volume levels and opening schedules."
            },
            {
                "execution": "parallel",
                "steps": [
                    {
                        "action": "system_control",
                        "control_type": "volume",
                        "target": 65
                    },
                    {
                        "action": "system_control",
                        "control_type": "brightness",
                        "target": 80
                    },
                    {
                        "action": "browser_search",
                        "engine": "google",
                        "query": "google calendar schedules"
                    }
                ]
            },
            {
                "action": "gesture_profile",
                "target": "presentation"
            },
            {
                "action": "speak",
                "target": "Meeting mode is ready. Laser pointer slide controls are online."
            }
        ]
    }
}
