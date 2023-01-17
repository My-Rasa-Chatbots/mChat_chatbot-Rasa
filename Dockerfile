FROM tensorflow/tensorflow
RUN mkdir -p /rasa-app
WORKDIR /rasa-app
COPY . /rasa-app

RUN pip3 install -r requirements.txt --use-feature=2020-resolver

RUN python -m spacy download em
RUN pip3 install --user rasa==3.1.0