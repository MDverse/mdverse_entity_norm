"""Scraps CSML molecules"""

import csv
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from ground_molecule import call_chebi, call_pubchem
from loguru import logger

URL = "https://charmm-gui.org/?doc=archive&lib=csml"
PAGE = httpx.get(URL)
SOUP = BeautifulSoup(PAGE.content, "html.parser")


def get_lipid_family_name(th) -> str | None:
    """Give the family name from a <th class='header'> tag.

    Parameters
    ----------
    th : beautifulsoup tag
        Represent the <th class='header'> element.

    Returns
    -------
    str | None
        The text in bold -> the family name
    """
    bold_tag = th.find("b")
    if bold_tag:
        return bold_tag.get_text(strip=True)
    return None


def build_grounding_name(short_name, long_name):
    """Build the grounding_name from the short_name and long_name.

    Parameters
    ----------
    short_name : str
        The short name of the lipid/residue.
    long_name : str
        The long name of the lipid/residue

    Returns
    -------
    str
        The grounding name, built from the short name and the long name(cleaned).
    """
    long_name = long_name.replace("+ LONEPAIR", "").strip()
    long_name = long_name.replace("+ LONE PAIR", "").strip()
    elements = []
    formula_regex = re.compile(r"^[A-Z]+[0-9]+([A-Z]{1,2}[0-9]*)*$")

    # We split the long name on ", "
    if long_name:
        for e in long_name.split(", "):
            if e:
                elements.append(e)

    formula = None
    full_name = None

    if len(elements) == 0:
        pass

    # If there is only one element, we check if it's a formula or a full name
    elif len(elements) == 1:
        if formula_regex.match(elements[0]):
            formula = elements[0]
        else:
            logger.info(f"For {elements} adding full name '{elements[0]}'")
            full_name = elements[0]

    else:
        # If there are multiple elements, we check if the first one is a formula or a full name
        if formula_regex.match(elements[0]):
            formula = elements[0]
            logger.info(f"For {elements} adding full name '{elements[0]}'")

            full_name = elements[1]
        else:
            logger.info(f"For {elements} adding full name '{elements[0]}'")
            full_name = elements[0]

    # We create the grounding name
    grounding_name = []
    # if short_name:
    # grounding_name.append(short_name)
    # if formula:
    # grounding_name.append(formula)
    if full_name:
        logger.info(
            f"Adding full name '{full_name}' to grounding name for short name '{short_name}'"
        )
        grounding_name.append(full_name)

    return " ".join(grounding_name), formula


def parse_data_row(row, current_family):
    """Extract short name and long name from a data row.

    Parameters
    ----------
    row : beautifulsoup tag
        Represent the <tr> element containing the data (<tr> = row).
    current_family : str
        The family name associated with the current data row, extracted from the header.

    Returns
    -------
    dict | None
        A dictionary with keys 'family', 'short_name', 'long_name', and 'grounding_name'
        or None if there is not valid informations.
    """
    cells = row.find_all("td")
    if len(cells) < 2:
        return None

    # We extract the short name from the first cell. If it's empty, we skip this row.
    short_name = cells[0].get_text(strip=True)
    if not short_name:
        return None
    # looks for a <font> tag inside the second cell to extract the long name,
    # because some long names are in a <font> tag.
    font_tag = cells[1].find("font")
    if font_tag:
        long_name = font_tag.get_text(strip=True)
    else:
        long_name = cells[1].get_text(strip=True)
    if not long_name:
        return None

    query_name, formula = build_grounding_name(short_name, long_name)

    return {
        "short_name": short_name,
        "formula": formula,
        "long_name": long_name,
        "query_name": query_name,
    }


def scrape_table(soup):
    """Scrape the table from the webpage and extract the relevant data.

    Parameters
    ----------
    soup : BeautifulSoup
        The BeautifulSoup object representing the parsed HTML content of the webpage.

    Returns
    -------
    list of dict
        A list of dictionaries, each containing the family, short name, long name,
        and grounding name for each lipid/residue entry found in the table.
    """
    results = []
    for header_th in soup.find_all("th", class_="header"):
        current_family = get_lipid_family_name(header_th)
        if not current_family:
            continue

        tbody = header_th.find_next_sibling("tbody")
        if not tbody:
            continue

        for row in tbody.find_all("tr"):
            entry = parse_data_row(row, current_family)
            if entry:
                results.append(entry)

    return results


def save_to_csv(results, filename):
    """Save the scrapped data to a CSV file.

    Parameters
    ----------
    results : list of dict
        The list of dictionaries containing the scrapped data.
    filename : Path
        The path to the output CSV file where the scraped data will be saved.
    """
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    scrapping_results = pd.DataFrame(results)
    scrapping_results.to_csv(filename, index=False)


def ground_one(grounding_name: str) -> dict:
    """Try to ground a single grounding_name via ChEBI then PubChem.

    Parameters
    ----------
    grounding_name : str
        The grounding name to look up.

    Returns
    -------
    dict
        A dict with keys: MOL, MOL_TYPE, ERRORS, MOL_ID, MOL_SCORE, MOL_FULL_NAME
    """
    result = call_chebi(grounding_name)
    if result and "error" not in result:
        return {
            "MOL": grounding_name,
            "MOL_TYPE": "CHEBI",
            "ERRORS": "No errors",
            "MOL_ID": result.get("chebi_id", "Not Available"),
            "MOL_SCORE": result.get("score", "Not Available"),
            "MOL_FULL_NAME": result.get("name", "Not Available"),
        }

    result = call_pubchem(grounding_name)
    if result and "error" not in result:
        return {
            "MOL": grounding_name,
            "MOL_TYPE": "PUBCHEM",
            "ERRORS": "No errors",
            "MOL_ID": result.get("id", "Not Available"),
            "MOL_SCORE": "Not Available",
            "MOL_FULL_NAME": result.get("name", "Not Available"),
        }

    return {
        "MOL": grounding_name,
        "MOL_TYPE": "Not found",
        "ERRORS": "No match in ChEBI or PubChem",
        "MOL_ID": "Not Available",
        "MOL_SCORE": "Not Available",
        "MOL_FULL_NAME": "Not Available",
    }


def ground_both(
    grounding_name: str, short_name: str, long_name: str, formula: str
) -> dict:
    """Ground a single grounding_name via ChEBI and PubChem.

    Parameters
    ----------
    grounding_name : str
        The grounding name to look up.
    short_name : str
        The short name of the lipid/residue.
    long_name : str
        The long name of the lipid/residue.
    formula : str
        The chemical formula of the lipid/residue.

    Returns
    -------
    dict
        A dict with keys: short_name, formula, long_name, chebi_query, pubchem_query,
        chebi_id, chebi_score, chebi_name, pubchem_id, pubchem_name
    """
    chebi = call_chebi(grounding_name) or {}
    pubchem = call_pubchem(grounding_name) or {}

    chebi_ok = (
        chebi.get("chebi_id") and chebi.get("formula", "Not Available") == formula
    )
    pubchem_ok = (
        pubchem.get("id")
        and pubchem.get("molecular_formula", "Not Available") == formula
    )

    if not chebi_ok:
        if short_name != grounding_name:
            chebi_fallback = call_chebi(short_name) or {}
            if (
                chebi_fallback.get("chebi_id")
                and chebi_fallback.get("formula", "Not Available") == formula
            ):
                chebi = chebi_fallback
                chebi_ok = True
        chebi_query = short_name
    else:
        chebi_query = grounding_name

    if not pubchem_ok:
        if short_name != grounding_name:
            pubchem_fallback = call_pubchem(short_name) or {}
            if (
                pubchem_fallback.get("id")
                and pubchem_fallback.get("molecular_formula", "Not Available")
                == formula
            ):
                pubchem = pubchem_fallback
                pubchem_ok = True
        pubchem_query = short_name
    else:
        pubchem_query = grounding_name

    return {
        "short_name": short_name,
        "formula": formula,
        "long_name": long_name,
        "chebi_query": chebi_query,
        "pubchem_query": pubchem_query,
        "chebi_id": chebi.get("chebi_id", "Not found") if chebi_ok else "Not found",
        "chebi_score": chebi.get("score", "Not found") if chebi_ok else "Not found",
        "chebi_name": chebi.get("name", "Not found") if chebi_ok else "Not found",
        "pubchem_id": pubchem.get("id", "Not found") if pubchem_ok else "Not found",
        "pubchem_name": pubchem.get("name", "Not found") if pubchem_ok else "Not found",
    }


def _grounding_sort_key(entry: dict) -> int:
    """Sort grounding results, prioritizing entries that were found in either ChEBI or PubChem.

    Parameters
    ----------
    entry : dict
        A dict with keys: query_name, chebi_id, chebi_score, chebi_name, pubchem_id, pubchem_name

    Returns
    -------
    int
        0 if the entry was found in either ChEBI or PubChem, 1 otherwise.
    """
    found = entry["chebi_id"] != "Not found" or entry["pubchem_id"] != "Not found"
    return 0 if found else 1


def save_grounding_to_tsv(grounding_results: list[dict], output_file: Path) -> None:
    """Save grounding results to a TSV file.

    Parameters
    ----------
    grounding_results : list[dict]
        List of grounding result dicts, one per lipid.
    output_file : Path
        Path to the output TSV file.
    """
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "short_name",
                "formula",
                "long_name",
                "chebi_query",
                "pubchem_query",
                "chebi_id",
                "chebi_score",
                "chebi_name",
                "pubchem_id",
                "pubchem_name",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(grounding_results)


@click.command()
@click.option(
    "--scraped_file",
    default="results/lipid_scrapping/csml_lipids.csv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the input file containing molecular identifiers",
)
@click.option(
    "--grounded_file",
    default="results/lipid_scrapping/csml_lipids_grounded.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the output TSV file with grounding results",
)
def scrap_lipids(scraped_file, grounded_file):
    """Scrape the lipid/residue data from the webpage and save it to a CSV file.

    Parameters
    ----------
    scraped_file : Path
        The path to the output CSV file where the scraped data will be saved.
    grounded_file : Path
        The path to the output TSV file where the grounding results will be saved.
    """
    lipid_scrapping = scrape_table(SOUP)
    save_to_csv(lipid_scrapping, scraped_file)

    lipid_grounding_results = []
    for entry in lipid_scrapping:
        grounded = ground_both(
            grounding_name=entry["query_name"],
            short_name=entry["short_name"],
            formula=entry["formula"],
            long_name=entry["long_name"],
        )
        lipid_grounding_results.append(grounded)
    lipid_grounding_results.sort(key=_grounding_sort_key)
    save_grounding_to_tsv(lipid_grounding_results, grounded_file)


if __name__ == "__main__":
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/ground_molecule_{timestamp}.log",
        level="DEBUG",
    )
    scrap_lipids()
