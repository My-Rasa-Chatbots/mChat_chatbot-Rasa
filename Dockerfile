FROM rasa/rasa:3.1.0-full

WORKDIR /app

COPY ./data /app/data
COPY ./config.yml /app/config.yml
COPY ./credentials.yml /app/credentials.yml
COPY ./domain.yml /app/domain.yml
COPY ./endpoints.yml /app/endpoints.yml

USER root

RUN rasa train

USER 1001