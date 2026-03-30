"""Module for using regex, sending requests and grounding.

re :This module provides regular expression matching operations.
requests : This module allows you to send HTTP/ requests.
gilda : This module allows Grounding Integrating Learned Disambiguation.
"""

import re

import gilda
import httpx
from loguru import logger

# API endpoints for different molecular databases
API_PDB = "https://data.rcsb.org/rest/v1/core/entry/"
API_UNIPROT = "https://rest.uniprot.org/uniprotkb/"
API_CHEBI = "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"


def get_type(entry: str):
    """Determine the molecular entity type based on regex pattern.

    Parameters
    ----------
    entry (str): The molecular identifier string to classify

    Returns
    -------
    str: The entity type ("PDB", "UNIPROT", "DNA", "RNA", or "CHEBI")
    """
    # PDB codes are 4 characters starting with a number
    if len(entry) == 4 and entry[0].isnumeric() and entry.isalnum():
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
    if re.search(r"^[atcg]+$", entry) is not None:
        return "DNA"
    # RNA sequence pattern
    if re.search(r"^[atucg]+$", entry) is not None:
        return "RNA"
    # Default to ChEBI for other chemical entities
    else:
        return "CHEBI"


def call_PDB(code_pdb: str):  # noqa: N802
    """Query the Protein Data Bank API for a given PDB code.

    Parameters
    ----------
    code_pdb (str): 4-character PDB identifier code

    Returns
    -------
    dict: Details retrieved from the PDB database (entry_id, pubmed_id, doi, emdb_id)
    """
    response = httpx.get(f"{API_PDB}{code_pdb}", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(f"PDB {code_pdb}: {response.url}")
        results = response.json()
        return {
            "pubmed_id": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_pub_med"
            ),
            "doi": results.get("rcsb_primary_citation", {}).get("pdbx_database_id_doi"),
            "title": results.get("struct", {}).get("title"),
            "rcsb_id": results.get("rcsb_id"),
        }
    else:
        logger.warning(
            f"Status HTTP : {response.status_code} "
            f"(The server can't process your request for `{code_pdb}`)"
        )


def call_uniprot(code_uniprot: str):
    """Query the UniProt API for a given UniProt accession code.

    Parameters
    ----------
    code_uniprot (str): UniProt accession identifier

    Returns
    -------
    dict: Details retrieved from the UniProt database (accession, uniprot_id, gene_name)
    """
    response = httpx.get(f"{API_UNIPROT}{code_uniprot}.json", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(f"UniProt {code_uniprot}: {response.url}")
        results = response.json()
        return {
            "accession": results.get("primaryAccession"),
            "uniprot_id": results.get("uniProtkbId"),
            "gene_name": results.get("genes", [{}])[0].get("geneName", {}).get("value"),
        }


def call_chebi(entity_name: str):
    """Query the ChEBI API for a given mollecule name.

    Parameters
    ----------
    entity_name (str): name of the compound

    Returns
    -------
    dict : Details retrieved from the chebi dtabase (id, score, name, stars)
    """
    parameters = {"term": entity_name, "page": 1, "size": 5}
    response = httpx.get(f"{API_CHEBI}", params=parameters, timeout=30)
    # If request is successful HTTP = 200
    if response.status_code == 200:
        logger.debug(
            f"Status HTTP : {response.status_code} "
            f"(The request succeeded for `{entity_name}`)"
        )
        results = response.json()["results"][0]
        return {
            "chebi_id": results["_id"],
            "score": results["_score"],
            "name": results["_source"]["ascii_name"],
            "star": results["_source"]["stars"],
        }
    else:
        logger.warning(
            f"Status HTTP : {response.status_code} "
            f"(The server can't process your request for `{entity_name}`)"
        )


def call_gilda(entity_name: str):
    """Query the GILDA module for a given mollecule name.

    Parameters.
    ----------
    entity_name (str): name of the compound

    Returns
    -------
    dict : Details retrieved from the chebi dtabase (id, score, name)
    """
    results = gilda.ground(entity_name)
    if results is not None and len(results) > 0:
        grounding_res = results[0].to_json()
        logger.info(
            f"Gilda grounding results found for `{entity_name}` : "
            f"{grounding_res['term']['id']}"
        )
        (logger.info(f"Database : {grounding_res['term']['db']}"),)
        result_dict = {
            "db": grounding_res["term"]["db"],
            "id": grounding_res["term"]["id"],
            "score": grounding_res["score"],
            "name": grounding_res["term"]["text"],
            "url": grounding_res["url"],
        }
        return result_dict
    else:
        logger.warning(f"No grounding results found for `{entity_name}` using GILDA.")


def grouding_mol_chebi(mol_file: str, ground_mol_file: str):
    """Ground the molecule to the chebi databases.

    Parameters
    ----------
    mol_file (str): Path to the input file containing molecular identifiers
    """
    # Open and read the MOL.txt file line by line
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entry\tType\tID_CHEBI\rName\tScore\tStars\n")
        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "CHEBI":
                result = call_chebi(line.strip())
                if result is not None:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\t{result['chebi_id']}\t{result['name']}\t{result['score']}\t{result['star']}\n"
                    )
                else:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tNot Found\tNot Found"
                        f"\tNA\tNot Found\n"
                    )


def grouding_mol_pdb(mol_file: str, ground_mol_file: str):
    """Ground the mollecule to the PDB database.

    Parameters
    ----------
    mol_file (str): Path to the input file containing molecular identifiers
    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\tID_PDB\tTittle\tpubmed_id\tdoi\n")
        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "PDB":
                result = call_PDB(line.strip())
                if result is not None:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\t{result['rcsb_id']}\t{result['title']}\t{result['pubmed_id']}\t{result['doi']}\n"
                    )
                else:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tNot Found\tNot Found"
                        f"\tNot Found\tNot Found\n"
                    )


def grouding_mol_uniprot(mol_file: str, ground_mol_file: str):
    """Ground the mollecule to the UniProt database.

    Parameters
    ----------
    mol_file (str): Path to the input file containing molecular identifiers
    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\tAccession\tID_UNIPROT\tgene_name\n")
        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "UNIPROT":
                result = call_uniprot(line.strip())
                if result is not None:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\t{result['accession']}\t{result['uniprot_id']}\t{result['gene_name']}\n"
                    )
                else:
                    f2.write(f"{line.strip()}\t{entity_type}\tNot Found\n")


def grounding_gilda(mol_file: str, ground_mol_file: str):
    """Create an output file containing the informations from the gild agrounding.

    Parameters.
    ----------
    mol_file (str) : name of the input file
    ROUND_mol_file (str) : name of the output file

    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tDatabase\tGilda_ID\tScore\tGilda_Name\tURL\n")

        for line in file_1:
            result = call_gilda(line.strip())

            if result:
                f2.write(
                    f"{line.strip()}\t{result['db']}\t{result['id']}\t{result['score']}\t{result['name']}\t{result['url']}\n"
                )
            else:
                f2.write(
                    f"{line.strip()}\tNOT_FOUND\tNOT_FOUND\tNA\tNOT_FOUND\tNOT_FOUND\n"
                )


if __name__ == "__main__":
    # Grounding the molecule to PDB database
    logger.info("Starting molecule grounding from PDB...")
    grouding_mol_pdb("data/MOL.txt", "results/ground_mol_pdb.tsv")
    logger.success("Molecule grounding completed.")
    # Grounding the molecule to uniprot database
    logger.info("Starting molecule grounding from UniProt...")
    grouding_mol_uniprot("data/MOL.txt", "results/ground_mol_uniprot.tsv")
    logger.success("Molecule grounding completed.")

    # # Grounding the molecule to chebi database
    logger.info("Starting molecule grounding from Chebi...")
    grouding_mol_chebi("data/MOL.txt", "results/ground_mol_chebi.tsv")
    logger.success("Molecule grounding completed.")
    # # Grounding the molecule with gilda
    logger.info("Starting Gilda grounding...")
    grounding_gilda("data/MOL.txt", "results/ground_mol_gilda.tsv")
    logger.success("Gilda grounding completed.")
