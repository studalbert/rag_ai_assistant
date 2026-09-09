# --- базовый образ ---
FROM python:3.11-slim

# не даём Python писать .pyc и буферизировать вывод — удобнее видеть логи в реальном времени
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
    
WORKDIR /code
    
# сначала копируем только requirements — так Docker закэширует этот слой,
# и при изменении кода (без изменения зависимостей) пересборка будет быстрой
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
    
# теперь копируем сам код и конфиги
COPY pyproject.toml .
COPY app ./app
COPY tests ./tests
    
EXPOSE 8000
    
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
