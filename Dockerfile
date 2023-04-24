FROM rasa/rasa:3.1.0-full

WORKDIR /app

COPY . /app
USER root
RUN rasa train

USER 1001