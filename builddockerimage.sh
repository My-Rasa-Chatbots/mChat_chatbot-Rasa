#!/bin/bash
########################################################
## Shell Script to Build Docker Image    
########################################################
### Rasa Open Source Server Build
##########################################

RASA_IMAGE_TAG=0.0.1
RASA_IMAGE_NAME=rasa-server-img

echo $RASA_IMAGE_NAME
echo "version: $RASA_IMAGE_TAG"

### DO NOT MODIFY ###
if [[ -z "$(docker images -q $RASA_IMAGE_NAME:$RASA_IMAGE_TAG)" ]]
then
  echo "Building rasa_server_image"
  docker build -t $RASA_IMAGE_NAME:$RASA_IMAGE_TAG .
else
  echo "Image already exists, change RASA_IMAGE_TAG"
fi
### DO NOT MODIFY ###


######################################################################
#### Action Server Build
######################################################################
echo "================="

RASA_ACTION_IMAGE_TAG=0.0.1
RASA_ACTION_IMAGE_NAME=action-server-img

echo $RASA_ACTION_IMAGE_NAME
echo "version: $RASA_ACTION_IMAGE_TAG"

### DO NOT MODIFY ###
if [[ -z "$(docker images -q $RASA_ACTION_IMAGE_NAME:$RASA_ACTION_IMAGE_TAG)" ]]
then
  echo "Building action_server image"
  docker build -t $RASA_ACTION_IMAGE_NAME:$RASA_ACTION_IMAGE_TAG actions
else
  echo "Image already exists, change RASA_ACTION_IMAGE_TAG"
fi
### DO NOT MODIFY ###

