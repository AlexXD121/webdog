# Base Image
FROM python:3.10-slim

# User Setup (Required by Hugging Face)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Working Directory
WORKDIR $HOME/app

# Dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Application Code
COPY --chown=user . .

# Network & Environment
EXPOSE 7860
ENV PORT=7860

# Start Command
CMD ["python", "webdog_bot/main.py"]
