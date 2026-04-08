"""Script to normalize the simlation times into standard units."""

import os
from datetime import UTC, datetime
from pathlib import Path

import click
import instructor
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()


class simulationTime(BaseModel):
    value: float | int | None = None
    unit: str | None = None


class norm_simu_time(BaseModel):
    input: str
    output: list[simulationTime]


PROMPT = """You are a unit normalization assistant for simulation time values.
Your task: Convert all time units to standard abbreviations (ps, ns, μs, ms, s)
and split values from units.

Rules:
- No markdown, no explanation.
- Standard units to use: ps (picoseconds), ns (nanoseconds), μs (microseconds),
    ms (milliseconds), s (seconds)
- Preserve the original order of values found in the text
- Always split value and unit (e.g. "500ns" → value: 500, unit: "ns")
- If there is an interval (e.g. "500-1000ns"), follow the ground truth exemple
- Take in consideration values written in letter (e.g. "one hundred"), and transfrom it
    to a numeric value
- If the unit is k or is missing define the normalized value of the unit to "None"
- If the value is missing define the normalized value to "None"
 """


def normalize_simulation_time(raw_simulation_time: str):
    """Normalize the units in the simulation time text to standard units.

    Parameters
    ----------
        simulation_time_filepath: Path to the input text file containing simulation time
        values.

    Returns
    -------
        A string containing the normalized simulation time values in JSON format.
    """
    client = instructor.from_openai(
        OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPEN_ROUTER_KEY"),
        )
    )

    # Read the input file
    # content = simulation_time_filepath.read_text()
    logger.info("Normalisation of simulation times ...")
    completion = client.chat.completions.create(
        model="openai/gpt-4o",
        response_model=norm_simu_time,
        messages=[
            {
                "role": "system",
                "content": f"{PROMPT}",
            },
            {
                "role": "user",
                "content": f"The simulation time you will be working on is : {raw_simulation_time}",
            },
        ],
    )
    logger.info("Normalisation of simulation times complete")
    if completion is None:
        logger.error("Error: No content in response")
        return ""
    else:
        logger.info(completion)
        logger.success("Normalisation of the data was successful")
        return completion.model_dump_json()


@click.command()
@click.option(
    "--raw_simulation_time",
    default="data/STIME.txt",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the input file containing the raw simulation times",
)
@click.option(
    "--normalized_simulation_time",
    default="results/normalized_simulation_time.txt",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the output file containing the simulation times",
)
def create_norm_simulation_time_file(
    raw_simulation_time: Path, normalized_simulation_time: Path
):
    """Create a txt file with the normalized values.

    Parameters
    ----------
    raw_simulation_time (Path) : Path to the input file containing
                                the raw simulation times
    normalized_simulation_time (Path) : Path to the output file containing
                                the normalized simulation times
    """
    with (
        open(raw_simulation_time) as file_1,
        open(normalized_simulation_time, "w") as file_2,
    ):
        for line in file_1:
            file_2.writelines(f"{normalize_simulation_time(line)}\n")


if __name__ == "__main__":
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/normalize_simulation_time{timestamp}.log",
        level="DEBUG",
    )
    example_simulation = [
        "10ns",
        "one hundred nanosecond",
        "multi-microsecond",
        "6microseconds",
        "100–200 ns",
        "1.5 micro-sec",
        "5-microsecond",
        "8 microseconds",
        "0.633 us",
    ]
    for example in example_simulation:
        # print(f"input : {example} output : {normalize_simulation_time(example)}")
        print(normalize_simulation_time(example))

    # create_norm_simulation_time_file()
