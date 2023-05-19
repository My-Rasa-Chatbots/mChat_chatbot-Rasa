RASA_CORE_IMAGE_TAG=0.0.1
RASA_ACTION_IMAGE_TAG=0.0.1


# echo "Rasa Server Tag: $RASA_CORE_IMAGE_TAG"
# echo "Action Server Tag: $RASA_ACTION_IMAGE_TAG"
echo -n "Do you want to proceed, (Type y/n)"
read VAR
if [[ $VAR == "y" ]] || [[ $VAR == "Y" ]]
then
  # IMAGES_LIST=$(docker image ls -a)
  # # echo $IMAGES_LIST
  # for IMG in $IMAGES_LIST
  # do
  #   echo $IMG
  # done

  echo "running docker containers"

  docker-compose -f docker-compose.dev.yml up -d
else
  echo "Exited!!"
fi
