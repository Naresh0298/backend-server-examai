# Use an official Python runtime as a parent image
# Changed from 3.13 to 3.11 for better Heroku compatibility and stability.
# You can choose other stable versions like 3.10, 3.12 if preferred and tested.
FROM python:3.11-slim-buster

# Set the working directory inside the container
WORKDIR /code

# Copy requirements.txt first for better Docker layer caching.
# If requirements.txt changes, only this layer and subsequent layers are rebuilt.
COPY requirements.txt /code/requirements.txt

# Install Python dependencies from requirements.txt.
# --no-cache-dir: Prevents pip from storing downloaded packages, reducing image size.
# --upgrade: Ensures pip itself is up-to-date.
# -r /code/requirements.txt: Installs packages listed in the requirements file.
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the application code from your local ./app directory to /code/app in the container.
COPY ./app /code/app

# Set Python path to include /code/app.
# This allows Python to correctly import modules like 'app.main_server'.
ENV PYTHONPATH="/code/app:${PYTHONPATH}"

# Create __init__.py files to make directories proper Python packages.
# This is crucial for 'app' and its containing directory '/code' to be recognized as Python packages.
RUN touch /code/__init__.py
RUN touch /code/app/__init__.py

# Expose port 8000 for local testing.
# IMPORTANT: Heroku itself will ignore this EXPOSE instruction for 'web' dynos.
# Your CMD instruction MUST bind to the $PORT environment variable Heroku provides.
EXPOSE 8000

# Command to run the application using Uvicorn.
# "app.main_server:app" is the Python import path to your FastAPI application instance.
# --host 0.0.0.0: Binds the server to all network interfaces within the container.
# --port $PORT: CRITICAL for Heroku! Uses the port assigned by Heroku environment variable.
CMD ["uvicorn", "app.main_server:app", "--host", "0.0.0.0", "--port", "${PORT}"]

# The commented-out Gunicorn CMD is an alternative for production deployments,
# offering more robust process management. If you switch to this, ensure gunicorn
# is in your requirements.txt and adjust "main:app" if your app path differs.
# # CMD ['gunicorn' main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT]
