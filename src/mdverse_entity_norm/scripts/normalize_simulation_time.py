"""Script to normalize the simlation times into standard units."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import click
import instructor
from dotenv import load_dotenv
from instructor.exceptions import InstructorRetryException
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


class SimulationTime(BaseModel):
    """Define the structure of simulation time entity."""

    value: float | None = Field(
        ..., description="Normalized value ofthe simulation time"
    )
    unit: str | None = Field(
        ..., max_length=2, description="Normalized unit ofthe simulation time"
    )


class NormSimuTime(BaseModel):
    """Define the structure for the output of the LLM."""

    input: str = Field(..., description="raw value of one simulaton time")
    output: list[SimulationTime] = Field(
        ..., description="normalized simulation timevalues and units"
    )


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


def load_simulation_times(raw_simu_times_file: Path) -> list:
    """Load simulation times from a file into a list.

    Parameters
    ----------
    raw_simu_times_file (Path): Path to the input file containing the simulation times

    Returns
    -------
    list: A list of  simulation times loaded from the file
    """
    logger.info(f"Loading the simulation times from {raw_simu_times_file}...")
    times = []
    with open(raw_simu_times_file) as file_1:
        for line in file_1:
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
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-4o",
            max_retries=3,
            response_model=NormSimuTime,
            messages=[
                {
                    "role": "system",
                    "content": f"{PROMPT}",
                },
                {
                    "role": "user",
                    "content": f"{raw_simulation_time}",
                },
            ],
        )
    except InstructorRetryException as exc:
        logger.warning(f"Failed after {exc.n_attempts} attempts")
        return None

    logger.info("Normalisation of simulation times complete")
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
    dict[list] : dictonarry that contains the results of the simulation times
    normalisation
    """
    all_simulation_times_norm = []
    normalisation_output = {}
    logger.info("Normalizing the simulation times...")
    for simulation_times in raw_simulation_time:
        normalize_time = normalize_simulation_time(simulation_times)
        if normalize_time:
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


def evaluate_normalisation(ground_truth_file: Path, normalized_simulation_time: Path):
    """Compare the LLM normalisation to the ground_truth to evaluate the normalisaion.

    Parameters
    ----------
    ground_truth_file (str) : Name of the ground truth file
    normalized_simulation_time (str) : Name of the file containing the results of the
                                 normalisation

    """
    logger.info("Evaluating the normalisation results...")
    with open(ground_truth_file) as file_1, open(normalized_simulation_time) as file_2:
        ground_truth = json.load(file_1)
        normalisation_results = json.load(file_2)
        ground_truth = ground_truth["groundtruth"]
        normalisation_results = normalisation_results["normalisation_output"]
    for results, truth in zip(normalisation_results, ground_truth):
        if results["input"] == truth["input"]:
            logger.info(
                f"same input for result and groundtruth : {results['input']} = "
                f"{truth['input']}"
            )
        else:
            logger.warning(
                f"different input for result and groundtruth : {results['input']} ≠"
                f" {truth['input']}"
            )
    for output_res, output_truth in zip(results["output"], truth["output"]):
        if output_res["value"] == output_truth["value"]:
            logger.info(
                f"same value for result and groundtruth : "
                f"{output_res['value']} = {output_truth['value']}"
            )
        else:
            logger.warning(
                f"different value for result and groundtruth : "
                f"{output_res['value']} ≠ {output_truth['value']}"
            )
        if output_res["unit"] == output_truth["unit"]:
            logger.info(
                f"same unit for result and groundtruth : "
                f"{output_res['unit']} = {output_truth['unit']}"
            )
        else:
            logger.warning(
                f"different unit for result and groundtruth : "
                f"{output_res['unit']} ≠ {output_truth['unit']}"
            )

    logger.success("Evaluation of the normalisation results complete")


@click.command()
@click.option(
    "--normalized_simulation_time",
    default="results/normalized_simulation_time_gpt.json",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the JSON output file containing the normalized simulation times",
)
@click.option(
    "--raw_simu_times_file",
    default="data/STIME.txt",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the input file containing the raw simulation times",
)
@click.option(
    "--ground_truth_file",
    default="data/STIME_ground_truth.json",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the groundtruth file",
)
def main_normalizing_simulation_times(
    raw_simu_times_file: Path, normalized_simulation_time: Path, ground_truth_file: Path
):
    """Normalize the simulation times entities bu running all annexe functions."""
    times = load_simulation_times(raw_simu_times_file)
    times = times[:5]
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
        "1069 ns",
        "1.6 ns",
        "4-microsecond",
        "500 ps",
        "200 to 300 ns",
        "300 nanoseconds",
        "700ns",
        "3 μs",
        "0.5μs",
        "157 nanosecs",
    ]
    normalisation_output = format_norm_simulation_time(example_simulation)
    print(normalisation_output)
    save_norm_simulation_results(normalisation_output, normalized_simulation_time)
    evaluate_normalisation(ground_truth_file, normalized_simulation_time)


if __name__ == "__main__":
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/normalize_simulation_time{timestamp}.log",
        level="DEBUG",
    )
    main_normalizing_simulation_times()
