FROM python:3.9.5-slim
#
# Install packages needed by the buildchain
#

RUN apt-get upgrade
RUN apt-get --assume-yes update \
 && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --assume-yes \
    build-essential \
    ca-certificates \
    curl \
    git \
    libssl-dev \
    openssh-client \
    python \
    python3 \
    python3-dev \
    python3-pip \
    python3-pkg-resources \
    python3-setuptools \
    python-dev \
    python-pip \
    python-pkg-resources \
    python-setuptools \
    sudo \
    tox \
    wget


WORKDIR /app
COPY ./requirements.txt .
RUN pip3 install -r ./requirements.txt

COPY runners_manager /app

CMD python3 ./main.py
