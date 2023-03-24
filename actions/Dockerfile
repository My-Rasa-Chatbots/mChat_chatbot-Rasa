FROM rasa/rasa-sdk:3.1.3

WORKDIR /app

USER root

ENV MONGODB_URL_LOCAL=mongodb://localhost:27017
ENV MONGODB_RESPONSE_DB=socket-chatbot

COPY ./ /app/actions

RUN python -m pip install -r ./actions/requirements.txt --no-cache

USER 1001