"""Script to ground molecule entities using various databases and compare results."""

import csv
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx
import pandas as pd
from loguru import logger

# API endpoints for different molecular databases
API_PDB = "https://data.rcsb.org/rest/v1/core/entry/"
API_UNIPROT = "https://rest.uniprot.org/uniprotkb/"
# API_CHEBI = "https://www.ebi.ac.uk/chebi/backend/api/public/advanced_search/"
API_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
API_LIGAND = "https://data.rcsb.org/rest/v1/core/chemcomp/"

NOT_WANTED_WORD = ["inhibitor", "agonist"]


def load_molecule(file_path: Path) -> list:
    """Load molecular identifiers from a file into a list.

    Parameters
    ----------
    file_path (Path): Path to the input file containing molecular identifiers

    Returns
    -------
    list: A list of molecular identifiers loaded from the file
    """
    logger.info(f"Loading MOL entities from {file_path}...")
    entities = pd.read_csv(file_path, sep="\t")
    mol_entities = entities[entities["category"] == "MOL"]
    mol_entities = list(mol_entities["entity"].unique())
    molecule_liste = []
    for molecule in mol_entities:
        if len(molecule) > 3:
            for word in NOT_WANTED_WORD:
                if word not in molecule:
                    molecule_liste.append(molecule)
    molecule_liste = list(set(molecule_liste))
    logger.info(f"Loaded {len(molecule_liste)} MOL entities successfully.")
    return molecule_liste


# def load_molecule(file_path: Path) -> list[str]:
#     """Load grounding candidates from the csml CSV file.

#     Parameters
#     ----------
#     file_path : Path
#         Path to the csml CSV file.

#     Returns
#     -------
#     list[str]
#         List of unique grounding names ready for grounding.
#     """
#     logger.info(f"Loading grounding names from {file_path}...")
#     df = pd.read_csv(file_path)
#     molecules = df["grounding_name"].dropna().unique().tolist()
#     logger.info(f"Loaded {len(molecules)} grounding names successfully.")
#     return molecules


# def create_ligand_dict(molecule_list: list):
#     """Create a list of molecule that are also ligand.

#     Prameters
#     ---------
#     molecule_list(list) : list of molecule names to verify

#     Returns
#     -------
#         list: LIst of ligand found in the PDB
#     """
#     ligand = []
#     for molecule in molecule_list:
#         response = httpx.get(f"{API_LIGAND}{molecule}", timeout=10)
#         if response.status_code == 200:
#             logger.success(f"Ligand found for {molecule}")
#         else:
#             logger.error(
#                 f"No ligand found for {molecule} error : {response.status_code}"
#             )

#     return ligand


def get_type(entry: str) -> str | None:
    """Determine the molecular entity type based on regex pattern.

    Parameters
    ----------
    entry (str): The molecular identifier string to classify

    Returns
    -------
    str | None : The entity type ("PDB", "UNIPROT", "DNA", "RNA").
                Otherwise, return None for others.
    """
    entry = entry.replace("`", "'")
    entry = entry.replace("’", "'")
    logger.info(entry)
    # Replace backticks with single quotes for sequence patterns
    # PDB codes are 4 characters starting with a number
    if re.search(r"^[1-9]([a-z]|[1-9]){3}$", entry) is not None:
        return "PDB"
    # UniProt accession pattern matching
    if (
        re.search(
            r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}",
            entry,
        )
        is not None
    ):
        return "UNIPROT"
    # DNA sequence pattern (only a, t, c, g)
    if re.search(r"^5'-[atcg]+-3'$", entry) is not None:
        return "DNA"
    # RNA sequence pattern
    if re.search(r"^5'-[aucg]+-3'$", entry) is not None:
        return "RNA"
    # # Amino acid sequence pattern
    if (
        re.search(r"^(?!^[agct]+$)[acdefghiklmnpqrstvwy]+$", entry) is not None
        and len(entry) > 4
    ):
        return "PROTEIN"


API_CHEBI = "https://www.ebi.ac.uk/ols4/api/search"


def call_chebi(entity_name: str) -> dict:
    logger.info(f"Searching for `{entity_name}` in ChEBI database (OLS4)...")

    params = {
        "ontology": "chebi",
        "q": entity_name,
        "queryFields": "label,synonym",
        "rows": 10,
    }

    try:
        response = httpx.get(API_CHEBI, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            docs = data.get("response", {}).get("docs", [])

            if not docs:
                logger.warning(f"No OLS4/ChEBI results found for `{entity_name}`")
                return {
                    "entity_name": entity_name,
                    "error": "No results found",
                    "API": "CHEBI",
                }

            best = docs[0]
            chebi_id = best.get("obo_id", "Not Available").replace("CHEBI:", "")

            logger.success(f"OLS4/ChEBI grounding successful for `{entity_name}`.")
            return {
                "entity_name": entity_name,
                "database": "CHEBI",
                "id": chebi_id,
                "score": data.get("responseHeader", {}).get("QTime", "Not Available"),
                "name": best.get("label", "Not Available"),
                "nb_res": data.get("response", {}).get("numFound", 0),
            }

        else:
            logger.warning(
                f"Failed to ground `{entity_name}` in OLS4/ChEBI (HTTP {response.status_code})."
            )
            return {
                "entity_name": entity_name,
                "error": f"HTTP {response.status_code}",
                "API": "CHEBI",
            }

    except Exception as e:
        logger.exception(f"Exception while querying OLS4/ChEBI for `{entity_name}`")
        return {"entity_name": entity_name, "error": str(e), "API": "CHEBI"}


# def call_chebi(entity_name: str) -> dict:
#     """
#     Query the ChEBI advanced_search API for a given molecule name.

#     Parameters
#     ----------
#     entity_name : str
#         Name of the compound.

#     Returns
#     -------
#     dict
#         Details retrieved from the ChEBI database or errors found during grounding.
#     """
#     logger.info(f"Searching for `{entity_name}` in ChEBI database...")

#     parameters = {"page": 1, "size": 15, "three_star_only": False}

#     payload = {
#         "text_search_specification": {
#             "and_specification": [{"text": entity_name, "category": "name"}]
#         },
#     }
#     try:
#         response = httpx.post(API_CHEBI, params=parameters, json=payload, timeout=30)

#         if response.status_code == 200:
#             logger.debug(
#                 f"From ChEBI: `{entity_name}` -> "
#                 f"HTTP {response.status_code} (request succeeded)"
#             )

#             data = response.json()

#             if not data.get("results"):
#                 logger.warning(f"No ChEBI results found for `{entity_name}`")

#                 return {
#                     "entity_name": entity_name,
#                     "error": "No results found",
#                     "API": "CHEBI",
#                 }

#             results = data["results"][0]

#             score = results.get("_score", 0)

#             if score < 0:
#                 logger.warning(
#                     f"From ChEBI: `{entity_name}` found but score {score} < 20"
#                 )

#                 return {
#                     "entity_name": entity_name,
#                     "error": "Score < 20",
#                     "API": "CHEBI",
#                 }

#             logger.success(f"ChEBI grounding successful for `{entity_name}`.")

#             return {
#                 "entity_name": entity_name,
#                 "database": "CHEBI",
#                 "id": results.get("_id", "Not Available"),
#                 "score": score,
#                 "name": results.get("_source", {}).get("ascii_name", "Not Available"),
#                 "star": results.get("_source", {}).get("stars", "Not Available"),
#                 "nb_res": data.get("total", 0),
#             }

#         else:
#             logger.warning(
#                 f"Failed to ground `{entity_name}` "
#                 f"in ChEBI database (HTTP {response.status_code})."
#             )

#             return {
#                 "entity_name": entity_name,
#                 "error": f"HTTP {response.status_code}",
#                 "API": "CHEBI",
#             }

#     except Exception as e:
#         logger.exception(f"Exception while querying ChEBI for `{entity_name}`")

#         return {
#             "entity_name": entity_name,
#             "error": str(e),
#             "API": "CHEBI",
#         }


def call_pdb(code_pdb: str) -> dict:
    """Query the Protein Data Bank API for a given PDB code.

    Parameters
    ----------
    code_pdb (str): 4-character PDB identifier code

    Returns
    -------
    dict: Details retrieved from the PDB database (entry_id, pubmed_id, doi, emdb_id)
    """
    logger.info(f"Searching for `{code_pdb}` in PDB database...")
    # The ressults_found contains :
    # - entry_id : The PDB identifier code
    # - pubmed_id : The PubMed ID of the primary citation associated with the PDB entry
    # - doi : The DOI of the primary citation associated with the PDB entry
    # - title : The title of the PDB entry
    # - rcsb_id : The RCSB ID of the PDB entry
    response = httpx.get(f"{API_PDB}{code_pdb}", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(
            f"From PDB {code_pdb}: for {code_pdb} ->"
            f"Status HTTP : {response.status_code}"
            f"(The request succeeded`)"
        )
        results = response.json()
        logger.success(f"ChEBI grounding successful for `{code_pdb}`.")
        return {
            "entity_name": code_pdb,
            "database": "PDB",
            "pubmed_id": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_pub_med", "Not Available"
            ),
            "doi": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_doi", "Not Available"
            ),
            "name": results.get("struct", {}).get("title", "Not Available"),
            "id": results.get("rcsb_id", "Not Available"),
        }
    else:
        logger.warning(
            f"Failed to ground `{code_pdb}` "
            f"in PDB database (HTTP {response.status_code})."
        )
        return {
            "entity_name": code_pdb,
            "error": f"HTTP {response.status_code}",
            "API": "PDB",
        }


def call_uniprot(code_uniprot: str) -> dict:
    """Query the UniProt API for a given UniProt accession code.

    Parameters
    ----------
    code_uniprot (str): UniProt accession identifier

    Returns
    -------
    dict: Details retrieved from the UniProt database (accession, uniprot_id, gene_name)
    """
    # The ressults_found contains :
    # - accession : The primary accession number of the UniProt entry
    # - uniprot_id : The UniProtKB identifier (entry name)
    # - gene_name : The primary gene name associated with the UniProt entry
    response = httpx.get(f"{API_UNIPROT}{code_uniprot}.json", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(
            f"from UniProt: for {code_uniprot} : ->"
            f"Status HTTP : {response.status_code}"
            f"(The request succeeded`)"
        )
        results = response.json()
        logger.success(f"PubChem grounding successful for `{code_uniprot}`.")

        return {
            "entity_name": code_uniprot,
            "database": "UniProt",
            "accession": results.get("primaryAccession"),
            "id": results.get("uniProtkbId"),
            "gene_name": results.get("genes", [{}])[0].get("geneName", {}).get("value"),
        }

    else:
        logger.warning(
            f"Failed to ground `{code_uniprot}`"
            f" in UNIPROT database (HTTP {response.status_code})."
        )
        return {
            "entity_name": code_uniprot,
            "error": f"HTTP {response.status_code}",
            "API": "UNIPROT",
        }


# def call_pubchem(entity_name: str) -> dict:
#     """Query the PubChem API for a given molecule name.

#     Parameters
#     ----------
#     entity_name (str): name of the compound

#     Returns
#     -------
#     dict : Details retrieved from PubChem (cid, full_name)
#     """
#     # The ressults_found contains :
#     # - cid : The PubChem Compound ID (CID) of the entity
#     # - full_name : The IUPAC name of the entity
#     # - molecular_formula : The molecular formula of the entity
#     response = httpx.get(
#         f"{API_PUBCHEM}/compound/name/{entity_name}/property/IUPACName,MolecularFormula/JSON",
#         timeout=100,
#     )
#     if response.status_code == 200:
#         if len(response.json()["PropertyTable"]["Properties"][0]) > 0:
#             results = response.json()["PropertyTable"]["Properties"][0]
#             logger.debug(
#                 f"from PubChem: for {entity_name} : -> Status HTTP : {response.status_code}"
#                 f"(The request succeeded)"
#             )
#             # results = response.json()["PropertyTable"]["Properties"][0]
#             logger.success(f"PubChem grounding successful for `{entity_name}`.")
#             return {
#                 "entity_name": entity_name,
#                 "database": "PubChem",
#                 "id": results.get("CID", "Not Available"),
#                 "name": results.get("IUPACName", "Not Available"),
#                 "molecular_formula": results.get("MolecularFormula", "Not Available"),
#             }
#         else:
#             logger.warning(
#                 f"Failed to ground `{entity_name}`"
#                 f" in Pubchem database (HTTP {response.status_code})."
#             )
#             return {
#                 "entity_name": entity_name,
#                 "error": "empty response",
#                 "API": "PUBCHEM",
#             }

#     else:
#         logger.warning(
#             f"Failed to ground `{entity_name}`"
#             f" in Pubchem database (HTTP {response.status_code})."
#         )
#         return {
#             "entity_name": entity_name,
#             "error": f"HTTP {response.status_code}",
#             "API": "PUBCHEM",
#         }


def call_pubchem(entity_name: str) -> dict:
    response = httpx.get(
        f"{API_PUBCHEM}/compound/name/{entity_name}/property/IUPACName,MolecularFormula/JSON",
        timeout=100,
    )
    if response.status_code == 200:
        try:
            results = response.json()["PropertyTable"]["Properties"][0]
        except (KeyError, IndexError, json.JSONDecodeError):
            logger.warning(f"PubChem returned no usable data for `{entity_name}`.")
            return {
                "entity_name": entity_name,
                "error": "empty response",
                "API": "PUBCHEM",
            }

        logger.success(f"PubChem grounding successful for `{entity_name}`.")
        return {
            "entity_name": entity_name,
            "database": "PubChem",
            "id": results.get("CID", "Not Available"),
            "name": results.get("IUPACName", "Not Available"),
            "molecular_formula": results.get("MolecularFormula", "Not Available"),
        }
    else:
        logger.warning(
            f"Failed to ground `{entity_name}` in PubChem (HTTP {response.status_code})."
        )
        return {
            "entity_name": entity_name,
            "error": f"HTTP {response.status_code}",
            "API": "PUBCHEM",
        }


# def call_pubchem(entity_name: str) -> dict:

#     response = httpx.get(
#         f"{API_PUBCHEM}/compound/name/{entity_name}/synonyms/JSON",
#         timeout=100,
#     )

#     if response.status_code == 200:
#         try:
#             results = response.json()["InformationList"]["Information"][0]

#             synonyms = results.get("Synonym", [])

#         except (KeyError, IndexError, json.JSONDecodeError):
#             return {
#                 "entity_name": entity_name,
#                 "error": "empty response",
#                 "API": "PUBCHEM",
#             }

#         return {
#             "entity_name": entity_name,
#             "database": "PubChem",
#             "id": results.get("CID", "Not Available"),
#             "synonyms": synonyms[:10],
#         }

#     return {
#         "entity_name": entity_name,
#         "error": f"HTTP {response.status_code}",
#         "API": "PUBCHEM",
#     }


def call_sequence(entity_name: str) -> dict:
    """Ground a sequence using regex patterns.

    Parameters
    ----------
    entity_name (str): The sequence string to classify

    Returns
    -------
    dict: The sequence and its type or the error if the sequence type is not recognized
    """
    logger.info(f"Classifying sequence `{entity_name}`...")
    entity_type = get_type(entity_name)
    if entity_type == "PROTEIN":
        logger.success(f"Sequence `{entity_name}` classified as {entity_type}.")
        return {"entity_name": entity_name, "database": entity_type}
    if entity_type == "DNA":
        logger.success(f"Sequence `{entity_name}` classified as {entity_type}.")
        return {"entity_name": entity_name, "database": entity_type}
    if entity_type == "RNA":
        logger.success(f"Sequence `{entity_name}` classified as {entity_type}.")
        return {"entity_name": entity_name, "database": entity_type}
    else:
        logger.warning(
            f"Failed to classify sequence `{entity_name}` -> Unrecognized format."
        )
        return {
            "entity_name": entity_name,
            "error": "Unrecognized sequence",
            "API": "SEQUENCE",
        }


def ground_whole_molecule(molecule: str):
    """Ground molecules using ChEBI first, then PubChem only if ChEBI fails."""
    results_found = []
    results_not_found = []

    logger.info(f"Trying to ground `{molecule}` using ChEBI...")

    result = call_chebi(molecule)

    if "error" not in result:
        results_found.append(result)
        logger.success(
            f"ChEBI found `{molecule}` -> skipping PubChem and sequence search."
        )
        return results_found, results_not_found
    if "error" in result and result["error"] == "Score < 20":
        logger.info(f"{result['entity_name']} has a score under 20")

    logger.info(f"Trying to ground `{molecule}` using PubChem...")

    result = call_pubchem(molecule)

    if "error" not in result:
        results_found.append(result)

        logger.success(f"PubChem found `{molecule}` after ChEBI failure.")

        return results_found, results_not_found

    logger.info(f"Trying to classify `{molecule}` as a sequence...")

    result = call_sequence(molecule)

    if "error" not in result:
        results_found.append(result)
    else:
        results_not_found.append(result)

    logger.success(
        f"Molecule grounding completed : found {len(results_found)} molecules"
    )
    return results_found, results_not_found


# def ground_whole_molecule(molecule: str):
#     results_found = []
#     results_not_found = []

#     logger.info(f"Trying to ground `{molecule}` using ChEBI...")
#     result = call_chebi(molecule)
#     if "error" not in result:
#         results_found.append(result)

#     logger.info(f"Trying to ground `{molecule}` using PubChem...")
#     result = call_pubchem(molecule)
#     if "error" not in result:
#         results_found.append(result)

#     if not results_found:
#         logger.info(f"Trying to classify `{molecule}` as a sequence...")
#         result = call_sequence(molecule)
#         if "error" not in result:
#             results_found.append(result)
#         else:
#             results_not_found.append(result)

#     return results_found, results_not_found


def grouding_mol(molecules: list[str]) -> tuple[list[dict], list[dict]]:
    """Ground molecules from all databases.

    Parameters
    ----------
    molecules (ist[str]): List containing the raw molecule names

    Returns
    -------
    tuple[list[dict], list[str]]: Lists of molecules found and molecules not found
    during the grounding
    """
    logger.info("Starting molecule grounding from pubchem...")
    # The ressults_found contains :
    # - id : The pubchem identifier
    # - score : The score search
    # - name : The full name of the entity
    # - nb_res : The number of results found by the GILDA Grounding
    results_found = []
    results_not_found = []

    for molecule in molecules:
        if get_type(molecule) == "PDB":
            result = call_pdb(molecule)
            if "error" not in result:
                results_found.append(result)
            else:
                grounded, not_grounded = ground_whole_molecule(molecule)
                results_found.extend(grounded)
                results_not_found.extend(not_grounded)
        elif get_type(molecule) == "UNIPROT":
            result = call_uniprot(molecule)
            if "error" not in result:
                results_found.append(result)
            else:
                grounded, not_grounded = ground_whole_molecule(molecule)
                results_found.extend(grounded)
                results_not_found.extend(not_grounded)
        else:
            grounded, not_grounded = ground_whole_molecule(molecule)
            results_found.extend(grounded)
            results_not_found.extend(not_grounded)
    logger.success(
        f"Molecule grounding completed : found {len(results_found)} molecules"
    )
    return results_found, results_not_found


def save_found_results_into_tsv(
    grounding_results: list[dict],
    non_grounded_results: list[dict],
    output_file: Path,
) -> None:
    """Save grounding results into a TSV file.

    Parameters
    ----------
    grounding_results (list[dict]): List of dictionaries containing grounding results
    output_file (str): Path to the output TSV file to save the results
    """
    with open(output_file, "w", newline="") as grounded_molecule_file:
        writer = csv.writer(grounded_molecule_file, delimiter="\t")
        writer.writerow(
            [
                "MOL",
                "MOL_TYPE",
                "ERRORS",
                "MOL_ID",
                "MOL_SCORE",
                "MOL_FULL_NAME",
                "NB_results",
            ]
        )
        for result in grounding_results:
            writer.writerow(
                [
                    result.get("entity_name", "Not Available"),
                    result.get("database", "Not Available"),
                    result.get("error", "No errors"),
                    result.get("id", "Not Available"),
                    result.get("score", "Not Available"),
                    result.get("name", "Not Available"),
                    result.get("nb_res", "Not Available"),
                ]
            )
        for result in non_grounded_results:
            writer.writerow(
                [
                    result.get("entity_name", "Not Available"),
                    result.get("database", "Unknown"),
                    result.get("error", "Not Available"),
                    result.get("id", "Not Available"),
                    result.get("score", "Not Available"),
                    result.get("name", "Not Available"),
                    result.get("nb_res", "Not Available"),
                ]
            )


@click.command()
@click.option(
    "--mol_filepath",
    default="data/MOL.txt",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the input file containing molecular identifiers",
)
@click.option(
    "--grounded_mol_filepath",
    default="results/grounded_molecules.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the output file for grounded results",
)
def ground_molecules(mol_filepath: Path, grounded_mol_filepath: Path) -> None:
    """Ground all molecules in the input file and write results to output file."""
    # Load molecule enntities from txt file
    molecules = load_molecule(mol_filepath)
    # Possibility to filter only the 5 first molecules for testing
    molecules = molecules[:]
    # Grounding the molecule
    grounded_mols, not_grounded_mols = grouding_mol(molecules)
    save_found_results_into_tsv(grounded_mols, not_grounded_mols, grounded_mol_filepath)
    # print(len(create_ligand_dict(not_grounded_mols)))
    # print(create_ligand_dict(not_grounded_mols))


if __name__ == "__main__":
    # Grounding the molecule to PDB database
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/ground_molecule_{timestamp}.log",
        level="DEBUG",
    )
    ground_molecules()
