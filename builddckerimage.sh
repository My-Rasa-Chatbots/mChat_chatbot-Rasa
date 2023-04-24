#!/bin/bash
########################################################
## Shell Script to Build Docker Image    
########################################################
docker -v
echo 'Building rasa_server image'
RASA_IMAGE_TAG=0.0.3
docker build -t rasa-server-img:$RASA_IMAGE_TAG .
echo 'Building action_server image'
RASA_ACTION_IMAGE_TAG=0.0.3
docker build -t action-server-img:$RASA_ACTION_IMAGE_TAG actions