# Ensure signal handlers are registered when the app is loaded
try:
    from . import signals  # noqa: F401
except Exception:
    # Avoid import-time hard failures in environments where Django app registry isn't ready
    pass


