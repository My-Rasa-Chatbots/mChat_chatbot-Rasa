FROM rasa/rasa:3.1.0-full

WORKDIR /app

COPY . /app

USER 1001