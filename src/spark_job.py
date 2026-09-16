"""
The Spark path. Used when an uploaded file is too large for pandas to handle
comfortably (threshold set by SPARK_ROW_THRESHOLD, default 500,000 rows).

Be honest about this in your write-up: for a 3,000-row CSV, Spark is slower
than pandas because of JVM startup overhead. Spark earns its place when the
data no longer fits in one machine's memory, or when you want the aggregation
to run across a cluster. Demonstrating that you know WHEN to reach for Spark
is worth more than forcing it everywhere.

Run standalone:
    python src/spark_job.py data/samples/large_sales.csv data/output/aggregates
"""
from __future__ import annotations

import os
import sys


def build_spark(app_name: str = "csv-cleaner-analytics"):
    from pyspark.sql import SparkSession

    master = os.getenv("SPARK_MASTER_URL", "local[*]")
    return (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )


def run(input_path: str, output_dir: str) -> dict:
    from pyspark.sql import functions as F

    spark = build_spark()
    try:
        df = spark.read.csv(input_path, header=True, inferSchema=True)
        row_count = df.count()
        print(f"[spark] Loaded {row_count:,} rows from {input_path}")

        # Distributed cleaning: the same operations as the pandas path, but
        # executed across partitions instead of in one process.
        df = df.dropDuplicates()

        numeric_cols = [
            f.name for f in df.schema.fields
            if f.dataType.typeName() in ("integer", "long", "double", "float", "decimal")
        ]
        text_cols = [f.name for f in df.schema.fields if f.dataType.typeName() == "string"]

        for col in text_cols:
            df = df.withColumn(col, F.trim(F.col(col)))

        # Fill numeric nulls with the column median (approxQuantile is the
        # distributed-friendly way to get this - an exact median would force
        # a full sort across the cluster).
        for col in numeric_cols:
            null_count = df.filter(F.col(col).isNull()).count()
            if null_count:
                median = df.approxQuantile(col, [0.5], 0.01)
                if median:
                    df = df.fillna({col: median[0]})
                    print(f"[spark] Filled {null_count} nulls in {col} with {median[0]}")

        df.cache()
        os.makedirs(output_dir, exist_ok=True)

        outputs = {}

        # Cleaned data as Parquet: columnar, compressed, far faster to re-read
        # than CSV. This is the format the analytics layer should consume.
        cleaned_dir = os.path.join(output_dir, "cleaned_parquet")
        df.write.mode("overwrite").parquet(cleaned_dir)
        outputs["cleaned_parquet"] = cleaned_dir

        # Aggregations, only where the necessary columns actually exist.
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        value_col = next(
            (c for c in numeric_cols if c.lower() in ("total", "revenue", "amount", "sales")),
            numeric_cols[0] if numeric_cols else None,
        )

        if date_col and value_col:
            daily = (
                df.withColumn("day", F.to_date(F.col(date_col)))
                .groupBy("day")
                .agg(
                    F.sum(value_col).alias("total_value"),
                    F.count("*").alias("transactions"),
                    F.avg(value_col).alias("avg_value"),
                )
                .orderBy("day")
            )
            path = os.path.join(output_dir, "daily_aggregates")
            daily.write.mode("overwrite").parquet(path)
            outputs["daily_aggregates"] = path
            print(f"[spark] Wrote daily aggregates ({daily.count()} days)")

        for dim in ("region", "category", "product", "payment_method"):
            if dim in df.columns and value_col:
                agg = (
                    df.groupBy(dim)
                    .agg(
                        F.sum(value_col).alias("total_value"),
                        F.count("*").alias("transactions"),
                    )
                    .orderBy(F.desc("total_value"))
                )
                path = os.path.join(output_dir, f"by_{dim}")
                agg.write.mode("overwrite").parquet(path)
                outputs[f"by_{dim}"] = path
                print(f"[spark] Wrote aggregates by {dim}")

        return {"row_count": row_count, "outputs": outputs}
    finally:
        spark.stop()


def should_use_spark(row_count: int) -> bool:
    """Single place that decides pandas vs Spark, so the rule is easy to explain."""
    threshold = int(os.getenv("SPARK_ROW_THRESHOLD", "500000"))
    return row_count >= threshold


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/spark_job.py <input_csv> <output_dir>")
        sys.exit(1)
    result = run(sys.argv[1], sys.argv[2])
    print(f"[spark] Done: {result}")
