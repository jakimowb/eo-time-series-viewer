ARG QGIS_VERSION=latest
FROM  qgis/qgis:${QGIS_VERSION}
LABEL maintainer="Benjamin Jakimow <benjamin.jakimow@geo.hu-berlin.de>"
LABEL description="Container to test the EO Time Series Viewer"

SHELL ["/bin/bash", "-c"]

RUN apt update \
    &&  apt install -y \
         git-lfs \
         pyqt5-dev-tools \
     	 python3-pip \
     	 python3-venv \
     	 python3-h5py \
      	 python3-pyqt5.qtopengl \
      	 python3-netcdf4 \
    && apt autoremove -y \
    && apt clean


ENV VENV=/opt/venvs/eotsv
COPY ./requirements_dev.txt /tmp/

RUN python3 -m venv --system-site-packages $VENV \
     && source $VENV/bin/activate \
     && python3 -m pip install --no-cache-dir -r tmp/requirements_dev.txt

ENV PYTHONPATH="${PYTHONPATH}:/usr/share/qgis/python/plugins"

WORKDIR /src

# Set the entrypoint
ENTRYPOINT ["/bin/bash", "-c", "source ${VENV}/bin/activate && exec \"$@\"", "--"]