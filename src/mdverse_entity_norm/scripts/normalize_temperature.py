"""Module for using regex.

This module provides regular expression matching operations.
"""

import re

import matplotlib.pyplot as plt
import pandas as pd
from loguru import logger


def norm_temp(temp_str: str) -> tuple:
    """Normalize the value of a temperature.

    Parameters
    ----------
    temp_str (str): The raw value of the temperature

    Returns
    -------
    str: The normalized value of the temp_str
    """
    temp_str = temp_str.lower()  # We convert the temp_str to lowercase
    # Extraction of the temperature and unit with a regex and the
    # search method of the re module
    # The regex is composed of three groups:
    # - The first group matches the integer part:([0-9])+ allows to math one or more
    #   digit due to the "+" symbol
    # - The second group matches the decimal part: (\.?[0-9]+)? allows to match
    #   an optional decimal part due to the "?" symbol at the end of the group.
    #   This group consists of an optional dot due to the "\.?" but if present is
    #   necessary followed by one or more digits thanks to the "[0-9]+" part.
    # - The third group matches the unit: ( *°? *[a-z]*)? allows to match
    #   an optional unit because of the "?" symbol at the end of the group.
    #   This group consists of zero or more spaces, because of the "*" symbol,
    #   an optional degree symbol, then zero or more spaces, and zero or more letters.
    logger.info("Normalising temperature entities ...")
    # If the temperatue is anotated as room temperature or body temperature
    # we normalize it to the standard value
    if temp_str == "room temperature":
        return (293, "K")
    if temp_str == "human body temperature":
        return (310, "K")
    temperature_match = re.search(r"([0-9]+)(\.?[0-9]+)?( *°? *[a-z]*)?", temp_str)
    if temperature_match is None:
        return None, None
    logger.info("Found temperature entity...")
    temperature_integer_part = temperature_match.group(1)
    temperature_decimal_part = temperature_match.group(2)
    temperature_unit = temperature_match.group(3)
    # Fetching the temperature value and casting to int or float
    if temperature_decimal_part is not None:
        temperature_value = float(
            temperature_integer_part + temperature_decimal_part.strip()
        )
    else:
        temperature_value = int(temperature_integer_part)

    # Fetching the unit and converting to kelvin when needed
    if temperature_unit is not None:
        temperature_unit = temperature_unit.strip(" ")  # We remove the spaces
        temperature_unit = temperature_unit.strip("°")  # We remove the degree
        if temperature_unit == "":  # if there is no unit we assume it's kelvin
            temperature_unit = "k"
        elif "c" in temperature_unit:
            # if the unit is in celsius we convert it to kelvin
            temperature_value += 273.15
            temperature_unit = "k"

    return temperature_value, temperature_unit


def create_norm_temp_file(raw_temp_file: str, norm_temp_file: str):
    """Create a .tsv file containing the raw temperature value.

    the normalised temperature value and the normalised unit.

    Parameters
    ----------
    raw_temp_file (str) : name of the  input file containing the raw values
    norm_temp_file (str) : name of the input file with the normalised informations

    """
    df = pd.read_csv(raw_temp_file, sep="\t")
    temp_entities = df[df["category"] == "TEMP"]["entity"].tolist()

    with open(norm_temp_file, "w") as f2:
        f2.write(
            "raw_temperature\tnormalised_temperature\tnormalised_unit\tnormalized_result\n"
        )

        for raw_temp in temp_entities:
            temperature_value, temperature_unit = norm_temp(raw_temp)

            if temperature_value is not None:
                f2.write(
                    f"{raw_temp}\t{temperature_value}\t{temperature_unit}\t{str(temperature_value) + temperature_unit}\n"
                )
            else:
                f2.write(f"{raw_temp}\tERROR\tERROR\tERROR\n")


def visualize_entity_count(file_path):

    temp_normalisation_results = pd.read_csv(file_path, sep="\t")

    before = len(temp_normalisation_results["raw_temperature"].unique())
    after = len(temp_normalisation_results["normalized_result"].unique())

    plt.figure(figsize=(6, 5))

    labels = ["Before Grounding", "After Grounding"]
    values = [before, after]

    plt.bar(labels, values)

    plt.ylabel("Number of unique temperatures")
    plt.title("Unique Temperature Count")
    plt.tight_layout()
    plt.savefig("results/norm_temp/entity_count.png")


if __name__ == "__main__":
    # Testing different cases of temp normalisation
    examples_temperature = [
        "300",
        "300 k",
        "27",
        "300k",
        "0c",
        "37 celsius",
        "37°C",
        "310.15°K",
        "20 Celsius",
    ]
    for temperature in examples_temperature:
        print(f"norm_temp('{temperature}') = {norm_temp(temperature)}")

    create_norm_temp_file("data/entities.tsv", "results/norm_temp.tsv")
    visualize_entity_count("results/norm_temp.tsv")
