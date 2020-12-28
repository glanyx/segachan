FROM python:3
MAINTAINER https://github.com/glanyx/

ADD . /sweeperbot
WORKDIR /sweeperbot
RUN pip install .

CMD ["sweeperbot"]
