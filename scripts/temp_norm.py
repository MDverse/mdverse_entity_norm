"""Module for using regex.

This module provides regular expression matching operations.
"""

import re


def norm_temp(temp_str):
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
    temperature_match = re.search(r"([0-9]+)(\.?[0-9]+)?( *°? *[a-z]*)?", temp_str)
    if temperature_match is None:
        return "No matches found"
    temperature_integer_part = temperature_match.group(1)  # We fetch the integer part
    temperature_decimal_part = temperature_match.group(2)  # We fetch the decimal part
    temperature_unit = temperature_match.group(3)  # We fetch the unit part

    # Fetching the temperature value and casting to int or float
    if temperature_decimal_part is not None:
        temperature_value = (float)(
            temperature_integer_part + temperature_decimal_part.strip()
        )
    else:
        temperature_value = (int)(temperature_integer_part)

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

    temp_norm = (str)(
        temperature_value
    ) + temperature_unit  # We build the output string
    return temp_norm


if __name__ == "__main__":
    # Testing different cases of temp normalisation
    test = [
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
    for t in test:
        print(f"norm_temp('{t}') = {norm_temp(t)}")
