#!/bin/bash

########################################################

## Shell Script to Build Docker Image    

########################################################
echo 'Building rasa_server image'
RASA_IMAGE_TAG=0.0.1
sudo docker build -t rasa-server-img:$RASA_IMAGE_TAG . --remove-orphans

echo 'Building action_server image'
RASA_ACTION_IMAGE_TAG=0.0.1
sudo docker build -t action-server-img:$RASA_ACTION_IMAGE_TAG actions --remove-orphans