# Custom Spark image with the JARs we need pre-baked.
#
# Base: the official Apache Spark image (Bitnami's published images were
# retired in mid-2025; the official image is now the standard choice).
#
# Why bake JARs instead of using --packages?
#   --packages downloads from Maven Central on every job submit. That works
#   but it's slow, depends on network access, and produces noisy logs.
#   Production Spark deployments always ship pre-built fat images. Baking
#   the JARs gives us reproducible cold-starts and offline-able jobs.
#
# JAR set: Kafka source connector + ClickHouse JDBC driver.
FROM apache/spark:3.5.5

ARG SPARK_VERSION=3.5.5
ARG SCALA_VERSION=2.12
ARG KAFKA_CLIENT_VERSION=3.5.1
ARG COMMONS_POOL2_VERSION=2.11.1
ARG CLICKHOUSE_JDBC_VERSION=0.6.0

ENV JARS_DIR=/opt/spark/jars

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL -o $JARS_DIR/spark-sql-kafka-0-10.jar \
      https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -fsSL -o $JARS_DIR/spark-token-provider-kafka-0-10.jar \
      https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    curl -fsSL -o $JARS_DIR/kafka-clients.jar \
      https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/${KAFKA_CLIENT_VERSION}/kafka-clients-${KAFKA_CLIENT_VERSION}.jar && \
    curl -fsSL -o $JARS_DIR/commons-pool2.jar \
      https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/${COMMONS_POOL2_VERSION}/commons-pool2-${COMMONS_POOL2_VERSION}.jar && \
    curl -fsSL -o $JARS_DIR/clickhouse-jdbc.jar \
      https://repo1.maven.org/maven2/com/clickhouse/clickhouse-jdbc/${CLICKHOUSE_JDBC_VERSION}/clickhouse-jdbc-${CLICKHOUSE_JDBC_VERSION}-all.jar

WORKDIR /opt/job

# Pre-create the checkpoint directory with correct ownership.
# Docker named volumes adopt the mountpoint's permissions on first creation,
# so doing this here means the volume's root won't be owned by root:root.
RUN mkdir -p /opt/checkpoint && chown -R 185:185 /opt/checkpoint /opt/job

# Apache Spark image runs as `spark` (uid 185). Keep that for non-root execution.
USER 185
