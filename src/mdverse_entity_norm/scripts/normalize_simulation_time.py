"""Script to normalize the simlation times into standard units."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

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
- Take in consideration values written in letter (e.g. "one hundred"), and transfrom it
    to a numeric value
- If the unit is k or is missing define the normalized value of the unit to "None"
- If the value is missing define the normalized value to "None"
 """


def load_simulation_times(file_path: Path) -> list:
    """Load simulation times from a file into a list.

    Parameters
    ----------
    file_path (Path): Path to the input file containing the simulation times

    Returns
    -------
    list: A list of  simulation times loaded from the file
    """
    logger.info(f"Loading the simulation times from {file_path}...")
    times = []
    with open(file_path) as raw_simu_times_file:
        for line in raw_simu_times_file:
            times.append(line.strip())
    logger.success(f"Loaded {len(times)} simulation times successfully.")
    return times


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


def format_norm_simulation_time(raw_simulation_time: list) -> dict:
    """Format the normalized time to a JSON format with the normalized values.

    Parameters
    ----------
    raw_simulation_time (Path) : Path to the input file containing
                                the raw simulation times
    normalized_simulation_time (Path) : Path to the output file containing
                                the normalized simulation times

    Returns
    -------
    dict[list] : dictonarry that contains the results of the simulation times normalisation
    """
    all_simulation_times_norm = []
    normalisation_output = {}
    logger.info("Normalizing the simulation times...")
    for simulation_times in raw_simulation_time:
        normalize_time = normalize_simulation_time(simulation_times)
        normalize_time_to_dict = json.loads(normalize_time)
        all_simulation_times_norm.append(normalize_time_to_dict)
    normalisation_output["normalisation_output"] = all_simulation_times_norm
    logger.success("Normalizing the simulation times successfull")
    return normalisation_output


def save_norm_simulation_results(
    normalisation_output: dict, normalized_simulation_time: Path
):
    """Generate a JSON file with the results of the simulation times normalisation."""
    logger.info("Saving the normalisation results in the JSON file")
    with open(normalized_simulation_time, "w") as file_1:
        json.dump(normalisation_output, file_1, indent=4, ensure_ascii=False)
    logger.success("Saving results to JSON file successful")


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
    normalisation_output = format_norm_simulation_time(example_simulation)
    print(normalisation_output)
    save_norm_simulation_results(
        normalisation_output, Path("results/normalized_simulation_time.json")
    )
