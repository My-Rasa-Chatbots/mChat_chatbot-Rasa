FROM rasa/rasa-sdk:3.1.3

WORKDIR /app

USER root

COPY ./ /app/actions
COPY *global-bundle.pem /app/global-bundle.pem

RUN python -m pip install -r ./actions/requirements.txt --no-cache

USER 1001