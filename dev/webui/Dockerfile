FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN sed '/^pywin32==/d' /tmp/requirements.txt > /tmp/linux-requirements.txt && pip install --no-cache-dir -r /tmp/linux-requirements.txt pytest playwright
RUN playwright install --with-deps chromium
COPY . /app
COPY dev/webui/config.example.json /app/config.json
ENV WEBUI_GAMESTATE_PATH=/sandbox/games WEBUI_HOST=0.0.0.0 WEBUI_PORT=8099
CMD ["python", "-m", "webui.server"]
