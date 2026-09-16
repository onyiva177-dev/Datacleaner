# Airflow base image, with the pipeline's own dependencies layered on top.
# Pinning the Airflow version matters: Airflow's own dependency tree is strict
# and an unpinned upgrade will break the image at the worst possible moment.
FROM apache/airflow:2.9.3-python3.11

USER root

# psycopg2 and pyarrow need build tooling on some base images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/requirements.txt

# --constraint keeps pip from silently upgrading Airflow's own dependencies.
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONPATH=/opt/airflow

WORKDIR /opt/airflow
