# build & run docker image with

IMAGE_NAME=jakimowb/eotsv
docker rmi $IMAGE_NAME
docker buildx build -t $IMAGE_NAME -f .docker/Dockerfile .

IMAGE_NAME=jakimowb/eotsv
docker run --rm -it -v "$(pwd)":/src $IMAGE_NAME /bin/bash