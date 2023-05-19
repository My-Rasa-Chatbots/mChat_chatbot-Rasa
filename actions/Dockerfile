FROM rasa/rasa-sdk:3.1.3

LABEL org.opencontainers.image.source https://github.com/marlabs-chatbot/marlabs_chatbot-Rasa

WORKDIR /app

USER root

COPY ./ /app/actions

RUN python -m pip install -r ./actions/requirements.txt --no-cache

USER 1001