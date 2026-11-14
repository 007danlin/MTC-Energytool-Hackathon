FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home app && chown app:app /app
COPY --chown=app:app solution.py settings.py llm_client.py contracts.py dialogue.py retrieval.py web_retrieval.py hybrid_retrieval.py prompts.py consultant.py consultation_state.py integration.py consultation_http.py requirements.txt ./
USER app
CMD ["python", "solution.py"]
