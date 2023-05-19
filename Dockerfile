FROM rasa/rasa:3.1.0-full

LABEL org.opencontainers.image.source https://github.com/marlabs-chatbot/marlabs_chatbot-Rasa

WORKDIR /app

COPY ./data /app/data
COPY ./config.yml /app/config.yml
COPY ./credentials.yml /app/credentials.yml
COPY ./domain.yml /app/domain.yml
COPY ./endpoints.yml /app/endpoints.yml
COPY ./global-bundle.pem /app/global-bundle.pem

USER root

RUN rasa train

USER 1001