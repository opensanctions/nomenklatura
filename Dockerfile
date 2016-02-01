FROM python:2.7.10
MAINTAINER robbi5 <robbi5@robbi5.de>

RUN apt-get update -qq && \
  apt-get install -y libpq-dev curl git python-pip python-virtualenv build-essential python-dev \
        libxml2-dev libxslt1-dev libpq-dev apt-utils ca-certificates

RUN curl --silent --location https://deb.nodesource.com/setup_0.12 | sh
RUN apt-get install -y nodejs && curl -L https://www.npmjs.org/install.sh | sh
RUN npm install -g bower uglifyjs less


COPY . /app
WORKDIR /app
RUN pip install -r /app/requirements.txt
RUN pip install -e /app &&  rm -rf .git && bower --allow-root install
ENV NOMENKLATURA_SETTINGS /app/heroku_settings.py
CMD ["/app/contrib/docker-run.sh"]

EXPOSE 8080
