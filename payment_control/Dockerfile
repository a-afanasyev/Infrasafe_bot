FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY payment_control/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m payment
COPY --chown=payment:payment payment_control /app/payment_control
USER payment
EXPOSE 8101
CMD ["uvicorn", "payment_control.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8101", "--no-access-log"]
