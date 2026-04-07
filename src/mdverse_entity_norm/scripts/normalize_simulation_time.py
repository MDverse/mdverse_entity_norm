"""Script to normalize the simlation times into standard units."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

load_dotenv()

PROMPT = """You are a unit normalization assistant for simulation time values.
Your task: Convert all time units to standard abbreviations (ps, ns, μs, ms, s)
and split values from units.

Rules:
- No markdown, no explanation.
- The output must be an array of objects with these exact keys:
  "raw" (the original token as found), "value" (number), "unit" (standard unit).
- Standard units to use: ps (picoseconds), ns (nanoseconds), μs (microseconds),
    ms (milliseconds), s (seconds)
- Preserve the original order of values found in the text
- Always split value and unit (e.g. "500ns" → value: 500, unit: "ns")
- If there is an interval (e.g. "500-1000ns"), split it into two entries
    with the same unit (e.g. value: 500, unit: "ns" and value: 1000, unit: "ns")
- Take in consideration values written in letter (e.g. "one hundred"), and transfrom it
    to a numeric value
- If the unit is k or if there is no value or non standard unit, ignore the line
- The file you will be working on is """


def normalize_simulation_time(
    simulation_time_filepath: Path,
) -> str:
    """Normalize the units in the simulation time text to standard units.

    Parameters
    ----------
        simulation_time_filepath: Path to the input text file containing simulation time
        values.

    Returns
    -------
        A string containing the normalized simulation time values in JSON format.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_KEY"),
    )

    # Read the input file
    content = simulation_time_filepath.read_text()
    logger.info("Normalisation of simulation times ...")
    completion = client.chat.completions.create(
        model="openai/gpt-4o",
        messages=[
            {
                "role": "user",
                "content": f"{PROMPT}{content}",
            }
        ],
    )
    logger.info("Normalisation of simulation times complete")
    normalized_content = completion.choices[0].message.content
    if normalized_content is None:
        logger.error("Error: No content in response")
        return ""
    else:
        logger.success("Normalisation of the data was successful")
        return normalized_content.strip()


@click.command()
@click.option(
    "--raw_simulation_time",
    default="data/STIME.txt",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the input file containing the raw simulation times",
)
@click.option(
    "--normalized_simulation_time",
    default="results/normalized_simulation_time.tsv",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the output file containing the simulation times",
)
def save_normalised_simulation_time_into_tsv(
    raw_simulation_time: Path, normalized_simulation_time: Path
):
    """Save the normalized content to a TSV file.

    Parameters
    ----------
    normalized_simulation_time: The path to the output TSV file where the normalized
    simulation time values will be saved.
    """
    normalized_content = normalize_simulation_time(raw_simulation_time)
    elements = json.loads(normalized_content)
    header = ["raw\tvalue\tunit\n"]
    lines = []
    logger.info("Writting the normalised simulation time in the .csv file")
    for element in elements:
        lines.extend(f"{element['raw']}\t{element['value']!s}\t{element['unit']}\n")
    with open(normalized_simulation_time, "w") as normalized_file:
        normalized_file.write(header[0])
        normalized_file.writelines(lines)
    logger.info("The .csv file is complete")


if __name__ == "__main__":
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/normalize_simulation_time{timestamp}.log",
        level="DEBUG",
    )
    save_normalised_simulation_time_into_tsv()
