# RunPod Serverless ComfyUI — official worker base + on-start S3 model loader.
FROM runpod/worker-comfyui:5.8.5-base

# Custom nodes
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    cd rgthree-comfy && pip install -r requirements.txt 2>/dev/null || true

# Dependency for the S3 model-download script
RUN pip install --no-cache-dir boto3

COPY s3_download.py /s3_download.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
