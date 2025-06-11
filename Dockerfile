FROM python:3.10-slim-buster

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt /code/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the application code
COPY ./app /code/app

# Copy the gcs directory if it exists (based on your file structure, it seems gcs_service.py is in app/)
# COPY ./gcs /code/gcs

# Set Python path to include /code so modules can be imported
ENV PYTHONPATH="/code/app:${PYTHONPATH}"

# Create __init__.py files to make directories proper Python packages
RUN touch /code/__init__.py
RUN touch /code/app/__init__.py

EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main_server:app", "--host", "0.0.0.0", "--port", "8000"]

# CMD ['gunicorn' main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT]