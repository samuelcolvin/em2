# ===============================================
# python build stage
FROM python:3.7-alpine3.8 as build

RUN apk add -U gcc g++ musl-dev zlib-dev libuv libffi-dev make openssl-dev git jpeg-dev openjpeg libjpeg-turbo tiff-dev

RUN pip install -U pip setuptools
ADD ./requirements1.txt /home/root/requirements1.txt
RUN pip install -r /home/root/requirements1.txt
ADD ./requirements2.txt /home/root/requirements2.txt
RUN pip install -r /home/root/requirements2.txt
# get rid of unnecessary files to keep the size of site-packages and the final image down
RUN find /usr \
    -name '*.py[codxi]' -o \
    -name '*.pxd' -o \
    -name '*.c' -o \
    -name '*.h' -o \
    -name '*.txt' | xargs rm
RUN find /usr -name '__pycache__' -delete
RUN find /usr -name '*.dist-info'  | xargs rm -r

# ===============================================
# final image
FROM python:3.7-alpine3.8

COPY --from=build /usr/local/bin/atoolbox /usr/local/bin/
#COPY --from=build /lib/* /lib/
COPY --from=build /usr/lib/* /usr/lib/
COPY --from=build /usr/local/lib/python3.7/site-packages /usr/local/lib/python3.7/site-packages

ENV PYTHONUNBUFFERED=1 \
    APP_ON_DOCKER=1 \
    ATOOLBOX_SETTINGS=em2.settings.Settings
WORKDIR /home/root/

# could exclude some files, but would it actually save any space in the image?
ADD ./ /home/root/em2/
ARG COMMIT
ARG BUILD_TIME
ENV COMMIT=$COMMIT \
    BUILD_TIME=$BUILD_TIME

CMD ["atoolbox", "auto"]
