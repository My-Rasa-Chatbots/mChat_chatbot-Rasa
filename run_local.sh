RASA_CORE_IMAGE_TAG=0.0.1
RASA_ACTION_IMAGE_TAG=0.0.1


# echo "Rasa Server Tag: $RASA_CORE_IMAGE_TAG"
# echo "Action Server Tag: $RASA_ACTION_IMAGE_TAG"
echo -n "Do you want to proceed, (Type y/n)"
read VAR
if [[ $VAR == "y" ]] || [[ $VAR == "Y" ]]
then

  echo "running docker containers in local !!"

  docker-compose -f docker-compose.local.yml up -d
else
  echo "Exited!!"
fi
