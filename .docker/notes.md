# build & run docker image with

QGIS_VERSION=3.38
IMAGE_NAME=jakimowb/eotsv:$QGIS_VERSION
docker rmi $IMAGE_NAME
docker buildx build -t $IMAGE_NAME --build-arg QGIS_VERSION=$QGIS_VERSION -f .docker/Dockerfile .

docker buildx build -t $IMAGE_NAME -f .docker/Dockerfile .

IMAGE_NAME=jakimowb/eotsv
docker run --rm -it -v "$(pwd)":/src $IMAGE_NAME /bin/bash