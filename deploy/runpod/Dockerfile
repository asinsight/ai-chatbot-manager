# RunPod Serverless ComfyUI — 공식 워커 base + S3 모델 로딩
FROM runpod/worker-comfyui:5.8.5-base

# 커스텀 노드
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    cd rgthree-comfy && pip install -r requirements.txt 2>/dev/null || true

# S3 모델 다운로드 스크립트
RUN pip install --no-cache-dir boto3

COPY s3_download.py /s3_download.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
