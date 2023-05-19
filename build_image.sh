#!/bin/bash
########################################################
## Shell Script to Build Docker Image    
########################################################
### Rasa Open Source Server Build
##########################################

RASA_IMAGE_TAG=0.0.1
RASA_IMAGE_NAME=rasa-server-img-prod

## Set Image Name ######################
echo -n "Please specify Rasa Core Image Name: "
read NAME_S
if [[ $NAME_S != "" ]]
then
  RASA_IMAGE_NAME=$NAME_S
fi
echo "Image name: $RASA_IMAGE_NAME"

## Set Image Tag #######################
echo -n "Please specify tag/version: "
read TAG_S
if [[ $TAG_S != "" ]]
then
  RASA_IMAGE_TAG=$TAG_S
fi
echo "version: $RASA_IMAGE_TAG"

### DO NOT MODIFY ###########################
if [[ -z "$(docker images -q $RASA_IMAGE_NAME:$RASA_IMAGE_TAG)" ]]
then
  echo "Building rasa_server_image"
  echo -n "Do you want to proceed, (Type y/n)"
  read VAR
  if [[ $VAR == "y" ]] || [[ $VAR == "Y" ]]
  then
    docker build -t $RASA_IMAGE_NAME:$RASA_IMAGE_TAG .
  fi
else
    echo "Image already exists, change RASA_IMAGE_TAG"
fi
### DO NOT MODIFY ###


######################################################################
#### Action Server Build
######################################################################
echo "================="

RASA_ACTION_IMAGE_TAG=0.0.2
RASA_ACTION_IMAGE_NAME=action-server-img-prod


## Set Image Name ######################
echo -n "Please specify Action server Image Name: "
read NAME_A
if [[ $NAME_A != "" ]]
then
  RASA_ACTION_IMAGE_NAME=$NAME_A
fi
echo "Image name: $RASA_ACTION_IMAGE_NAME"

## Set Image Tag #######################
echo -n "Please specify tag/version: "
read TAG_A
if [[ $TAG_A != "" ]]
then
  RASA_ACTION_IMAGE_TAG=$TAG_A
fi
echo "version: $RASA_ACTION_IMAGE_TAG"

### DO NOT MODIFY ###
if [[ -z "$(docker images -q $RASA_ACTION_IMAGE_NAME:$RASA_ACTION_IMAGE_TAG)" ]]
then
  echo "Building action_server image"
  echo -n "Do you want to proceed, (Type y/n)"
  read VAR
  if [[ $VAR == "y" ]] || [[ $VAR == "Y" ]]
  then
    docker build -t $RASA_ACTION_IMAGE_NAME:$RASA_ACTION_IMAGE_TAG actions
  fi
else
  echo "Image already exists, change RASA_ACTION_IMAGE_TAG"
fi
### DO NOT MODIFY ###

