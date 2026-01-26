FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libavcodec-extra \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 设置 FFmpeg 多线程环境变量
ENV FFMPEG_THREADS=0
ENV PYDUB_FFMPEG_PATH=/usr/bin/ffmpeg

# 创建工作目录
WORKDIR /app

#mock directory for clearvoice
RUN mkdir /app/clearvoice && touch /app/clearvoice/__init__.py

COPY clearvoice/README.md /app/README.md
COPY clearvoice/pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir .

RUN pip install --no-cache-dir "gradio<6.0" silero-vad modelscope \
    && pip install "ttd_fastapi_utils>=0.2.4" --index-url http://pypi-server/simple/ --trusted-host pypi-server

# 复制应用代码
COPY ./clearvoice .

# 暴露端口
EXPOSE 8501

# 启动命令
#ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
CMD ["python", "gradio_app.py"]