FROM dockerfile/python
MAINTAINER robbi5 <robbi5@robbi5.de>

RUN \
  add-apt-repository -y ppa:chris-lea/node.js && \
  apt-get update && \
  apt-get install -y nodejs libpq-dev && \
  npm install -g bower less uglify-js

RUN virtualenv /env
ADD requirements.txt /app/
RUN /env/bin/pip install -r /app/requirements.txt

ADD . /app
WORKDIR /app

RUN /env/bin/python setup.py develop

VOLUME /app

ENV NOMENKLATURA_SETTINGS /app/heroku_settings.py

CMD ["/app/contrib/docker-run.sh"]

EXPOSE 8080