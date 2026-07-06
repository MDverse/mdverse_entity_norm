"""Script to count the number of LLM errors from logs."""

from pathlib import Path

import click
import pandas as pd
from loguru import logger


def extract_errors(lines: list[str]) -> list:
    """Extract the model, input, and output from the log lines.

    Returns
    -------
    list
        A list of lists, where each inner list contains the model, input, and output for
        each error found in the log lines.
    """
    results = []
    logger.info("Extracting errors from log lines...")
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

    logger.success(f"Extracted {len(results)} errors from log lines.")
    return results


@click.command()
@click.option(
    "--log-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the TSV file containing the entities.",
)
def main(log_file: Path):
    """Count the number of LLM errors from logs."""
    logger.info(f"Counting LLM errors from log file: {log_file}")
    # Load the log file and extract the lines
    try:
        with open(log_file, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error("Log file not found.")
        return
    except UnicodeDecodeError as e:
        logger.error(f"Error reading log file: {e}")
        return

    errors = extract_errors(lines)
    df_errors = pd.DataFrame(errors, columns=["model", "input", "result"])
    # Count the occurrences of each unique combination of model, input, and result
    counts = df_errors.value_counts().reset_index()
    counts.columns = ["model", "input", "result", "count"]
    # Add a total count for each model
    counts["total"] = counts.groupby("model")["count"].transform("sum")
    # Sort the DataFrame by total count and then by individual count
    sorted_df = counts.sort_values(by=["total", "count"], ascending=False)
    # Rearrange the columns to have total and count first
    sorted_df = sorted_df[["total", "count", "model", "input", "result"]]
    logger.debug(f"Sorted DataFrame:\n{sorted_df}")
    # Save the sorted DataFrame to a TSV file
    output_path = Path("results/STIME_normalized/llm_error_count.tsv")
    if not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_df.to_csv(output_path, sep="\t", index=False)


if __name__ == "__main__":
    main()
