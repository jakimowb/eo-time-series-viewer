# build & run docker image with

IMAGE_NAME=jakimowb/eotsv
docker buildx build -t $IMAGE_NAME -f .docker/Dockerfile -

docker run --rm -it -v "$(pwd)":/src IMAGE_NAME /bin/bash