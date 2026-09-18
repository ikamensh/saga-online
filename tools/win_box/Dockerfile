# The headless RDP client of tools/win_desktop.py: FreeRDP drawing into a virtual X display.
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends freerdp3-x11 xvfb xauth ca-certificates \
    && rm -rf /var/lib/apt/lists/*
