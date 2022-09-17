FROM quay.io/wakaba/docker-perl-app-base

ADD bin/ /app/bin/
ADD config/ /app/config/
ADD modules/ /app/modules/
ADD data/ /app/data/
ADD Makefile /app/
ADD *.cgi /app/
ADD *.html /app/
ADD *.js /app/
ADD *.css /app/

RUN cd /app && \
    make deps-docker PMBP_OPTIONS="--execute-system-package-installer --dump-info-file-before-die" && \
    echo '#!/bin/bash' > /server && \
    echo 'export LANG=C' >> /server && \
    echo 'export TZ=UTC' >> /server && \
    echo 'port=${PORT:-8080}' >> /server && \
    echo 'cd /app && SCHEMADB_READ_ONLY=1 ./plackup -p ${port} -s Twiggy::Prefork bin/server.psgi' >> /server && \
    chmod u+x /server && \
    rm -rf /var/lib/apt/lists/* /app/local/pmbp/tmp /app/deps

CMD ["/server"]

## License: Public Domain.
