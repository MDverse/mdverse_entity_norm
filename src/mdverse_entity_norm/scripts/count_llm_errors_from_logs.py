"""Script to count the number of LLM errors from logs."""

import sys

import pandas as pd
from loguru import logger


def check_argument():
    if len(sys.argv) < 2:
        print("Usage: uv run script.py <logfile>")
        sys.exit(1)

    file_name = sys.argv[1]

    with open(file_name) as f:
        lines = f.readlines()

    return lines


def extract_errors(lines):
    results = []
    logger.info("Extarcting input and output")
    for i in range(len(lines)):
        if "failed" in lines[i]:
            context = lines[max(0, i - 2) : i + 1]

            model = ""
            input_val = ""
            output = ""

            for line in context:
                if "Normalizing" in line:
                    parts_pipe = line.split("|")
                    if len(parts_pipe) > 2:
                        model = parts_pipe[2].strip()

                    parts_colon = line.split(":")
                    if len(parts_colon) > 3:
                        input_val = parts_colon[3].strip()

                if "SimulationTime" in line:
                    parts_colon = line.split(":")
                    if len(parts_colon) > 3:
                        output = parts_colon[3].strip()

                if "failed after" in line:
                    output = "failed after 3 attempts"

            results.append([model, input_val, output])

    return results


def compute_occurrences(df):
    counts = df.value_counts().reset_index()
    counts.columns = ["model", "input", "result", "count"]
    return counts


def add_model_totals(df):
    df["total"] = df.groupby("model")["count"].transform("sum")
    return df


def sort_results(df):
    return df.sort_values(by=["total", "count"], ascending=False)


def save_to_tsv(df, output_path="results/norm_simu_times/llm_error_count.tsv"):
    df.to_csv(output_path, sep="\t", index=False)


def main():
    lines = check_argument()

    data = extract_errors(lines)
    df = pd.DataFrame(data, columns=["model", "input", "result"])

    occurrences = compute_occurrences(df)
    occurrences = add_model_totals(occurrences)
    sorted_df = sort_results(occurrences)
    sorted_df = sorted_df[["total", "count", "model", "input", "result"]]

    print(sorted_df)
    save_to_tsv(sorted_df)


if __name__ == "__main__":
    main()
