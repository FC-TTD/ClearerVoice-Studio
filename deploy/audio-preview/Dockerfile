FROM clearvoice-audio-base:h-ff9a24184aa1
COPY clearvoice/clearvoice /app/clearvoice/clearvoice
COPY deploy/audio-preview/audio_api /app/audio_api
COPY deploy/audio-preview/native-revision /app/native-revision
ENV PYTHONPATH=/app:/app/clearvoice PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1
WORKDIR /srv/clearvoice
ENTRYPOINT []
CMD ["python","-m","uvicorn","audio_api.app:app","--host","0.0.0.0","--port","8000","--workers","1"]
