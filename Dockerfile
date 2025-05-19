FROM pytorch/pytorch:2.2.0-cuda12.2-cudnn8.9.2-runtime

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

#mount requirements.txt for best cache result
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install streamlit

# 复制应用代码
COPY ./clearvoice .

# 暴露端口
EXPOSE 8501

# 启动命令
ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
