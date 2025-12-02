FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    ffmpeg \
    libavcodec-extra \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 设置 FFmpeg 多线程环境变量
ENV FFMPEG_THREADS=0
ENV PYDUB_FFMPEG_PATH=/usr/bin/ffmpeg

# 创建工作目录
WORKDIR /app

#mount requirements.txt for best cache result
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements.txt

RUN pip install --no-cache-dir gradio silero-vad modelscope

# 复制应用代码
COPY ./clearvoice .

# 暴露端口
EXPOSE 8501

# 启动命令
#ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
CMD ["python", "gradio_app.py"]