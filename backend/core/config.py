# Backwards compatibility layer mapping global settings
from backend.config.settings import settings

# Bind all attributes from settings to this module's dictionary namespace
globals().update(settings.__dict__)
