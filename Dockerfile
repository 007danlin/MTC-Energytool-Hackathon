FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home app && chown app:app /app
COPY --chown=app:app solution.py settings.py llm_client.py contracts.py dialogue.py retrieval.py hybrid_retrieval.py prompts.py consultant.py integration.py consultation_http.py requirements.txt ./
USER app
CMD ["python", "solution.py"]
