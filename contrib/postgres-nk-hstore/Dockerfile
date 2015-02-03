FROM postgres:9.4

RUN mkdir -p /docker-entrypoint-initdb.d
ADD ./create_db.sh /docker-entrypoint-initdb.d/create_db.sh
RUN chmod +x /docker-entrypoint-initdb.d/*.sh