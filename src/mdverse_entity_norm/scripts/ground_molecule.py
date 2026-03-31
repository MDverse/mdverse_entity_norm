"""Module for using regex, sending requests and grounding.

re :This module provides regular expression matching operations.
requests : This module allows you to send HTTP/ requests.
gilda : This module allows Grounding Integrating Learned Disambiguation.
"""

import json
import re

import gilda
import httpx
import numpy as np
import pandas as pd
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
    if re.search(r"^5’-[atcg]+-3’$", entry) is not None:
        return "DNA"
    # RNA sequence pattern
    if re.search(r"^5’-[aucg]+-3’$", entry) is not None:
        return "RNA"
    # # Amino acid sequence pattern
    # [WIP : need another logic to avoid grounding Chebi entities as proteins]
    # if re.search(r"^(?!^[agct]+$)[acdefghiklmnpqrstvwy]+$", entry) is not None:
    #     return "PROTEIN"
    # Default to ChEBI/GILDA for other chemical entities
    else:
        return "CHEBI/GILDA"


# ------------------------------------------------------------------------------#
# Functions to call the APIs and retrieve the grounding information              #
# ------------------------------------------------------------------------------#


def call_pdb(code_pdb: str):
    """Query the Protein Data Bank API for a given PDB code.

    Parameters
    ----------
    code_pdb (str): 4-character PDB identifier code

    Returns
    -------
    dict: Details retrieved from the PDB database (entry_id, pubmed_id, doi, emdb_id)
    """
    # The result_dict contains :
    # - entry_id : The PDB identifier code
    # - pubmed_id : The PubMed ID of the primary citation associated with the PDB entry
    # - doi : The DOI of the primary citation associated with the PDB entry
    # - title : The title of the PDB entry
    # - rcsb_id : The RCSB ID of the PDB entry
    response = httpx.get(f"{API_PDB}{code_pdb}", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(f"PDB {code_pdb}: {response.url}")
        results = response.json()
        result_dict = {
            "pubmed_id": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_pub_med"
            ),
            "doi": results.get("rcsb_primary_citation", {}).get("pdbx_database_id_doi"),
            "title": results.get("struct", {}).get("title"),
            "rcsb_id": results.get("rcsb_id"),
        }
        return result_dict
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
    # The result_dict contains :
    # - accession : The primary accession number of the UniProt entry
    # - uniprot_id : The UniProtKB identifier (entry name)
    # - gene_name : The primary gene name associated with the UniProt entry
    response = httpx.get(f"{API_UNIPROT}{code_uniprot}.json", timeout=10)
    # If request is successful (HTTP 200), print the response links
    if response.status_code == 200:
        logger.info(f"UniProt {code_uniprot}: {response.url}")
        results = response.json()
        result_dict = {
            "accession": results.get("primaryAccession"),
            "uniprot_id": results.get("uniProtkbId"),
            "gene_name": results.get("genes", [{}])[0].get("geneName", {}).get("value"),
        }
        return result_dict
    else:
        logger.warning(
            f"Status HTTP : {response.status_code} "
            f"(The server can't process your request for `{code_uniprot}`)"
        )


def call_chebi(entity_name: str):
    """Query the ChEBI API for a given mollecule name.

    Parameters
    ----------
    entity_name (str): name of the compound

    Returns
    -------
    dict : Details retrieved from the chebi dtabase (id, score, name, stars)
    """
    # The result_dict contains :
    # - id : The ChEBI identifier
    # - score : The score search
    # - name : The full name of the entity
    # - nb_res : The number of results found by the GILDA Grounding
    parameters = {"term": entity_name, "page": 1, "size": 5}
    response = httpx.get(f"{API_CHEBI}", params=parameters, timeout=30)
    string_response = response.__dict__["_content"].decode()
    # If request is successful HTTP = 200
    if response.status_code == 200:
        logger.debug(
            f"Status HTTP : {response.status_code} "
            f"(The request succeeded for `{entity_name}`)"
        )
        results = response.json()["results"][0]
        result_dict = {
            "id": results["_id"],
            "score": results["_score"],
            "name": results["_source"]["ascii_name"],
            "star": results["_source"]["stars"],
            "nb_res": json.loads(string_response)["total"],
        }
        return result_dict
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
    dict : Details retrieved from the chebi database (id, score, name)
    """
    # The result_dict contains :
    # - db : The database from where the term has been grounded
    #        (here we force the database to be ChEBI)
    # - id : The ChEBI identifier
    # - score : The score search
    # - name : The full name of the entity
    # - url : The link to the entity page
    # - nb_res : The number of results found by the GILDA Grounding
    results = gilda.ground(entity_name, namespaces=["CHEBI"])
    if results is not None and len(results) > 0:
        grounding_res = results[0].to_json()
        logger.info(
            f"Gilda grounding results found for `{entity_name}` : "
            f"{grounding_res['term']['id']}"
        )
        (logger.info(f"Database : {grounding_res['term']['db']}"),)
        result_dict = {
            "db": grounding_res["term"]["db"],
            "id": grounding_res["term"]["id"].strip("CHEBI:"),
            "score": grounding_res["score"],
            "name": grounding_res["term"]["text"],
            "url": grounding_res["url"],
            "nb_res": len(results),
        }
        return result_dict
    else:
        logger.warning(f"No grounding results found for `{entity_name}` using GILDA.")


# ------------------------------------------------------------------------------#
# Functions to write the grounded molecule information to a file                #
# ------------------------------------------------------------------------------#


def grouding_mol_chebi(mol_file: str, ground_mol_file: str):
    """Create an output file containing the informations returned by call_chebi.

    Parameters
    ----------
    mol_file (str): Path to the input file containing molecular identifiers
    """
    # Open and read the MOL.txt file line by line
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\tDatabase\tID\tScore\tName\tStars\tnb_res\n")
        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "CHEBI/GILDA":
                result = call_chebi(line.strip())
                if result is not None:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tCHEBI\t{result['id']}\t{result['score']}\t{result['name']}\t{result['star']}\t{result['nb_res']}\n"
                    )
                else:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tCHEBI\tNOT_FOUND\t{np.nan}\tNOT_FOUND\tNOT_FOUND\tNOT_FOUND\n"
                    )


def grouding_mol_pdb(mol_file: str, ground_mol_file: str):
    """Create an output file containing the informations returned by call_pdb.

    Parameters
    ----------
    mol_file (str): Path to the input file containing molecular identifiers
    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\tID_PDB\tTittle\tpubmed_id\tdoi\n")
        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "PDB":
                result = call_pdb(line.strip())
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
    """Create an output file containing the informations returned by call_uniprot.

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
    """Create an output file containing the informations returned by call_gilda.

    Parameters.
    ----------
    mol_file (str) : name of the input file
    ground_mol_file (str) : name of the output file

    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\tDatabase\tID\tScore\tName\tURL\tnb_res\n")

        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type == "CHEBI/GILDA":
                result = call_gilda(line.strip())
                if result is not None:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\t{result['db']}\t{result['id']}\t{result['score']}\t{result['name']}\t{result['url']}\t{result['nb_res']}\n"
                    )
                else:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tNOT_FOUND\tNOT_FOUND\t{np.nan}\tNOT_FOUND\tNOT_FOUND\tNOT_FOUND\n"
                    )


def grounding_sequence(mol_file: str, ground_mol_file: str):
    """Create an output file containing the grounded sequence information.

    Parameters.
    ----------
    mol_file (str) : name of the input file containing the raw data
    ground_mol_file (str) : name of the output file containing the grounded sequence

    """
    with open(mol_file) as file_1, open(ground_mol_file, "w") as f2:
        f2.write("Entity_name\tType\n")

        for line in file_1:
            entity_type = get_type(line.strip())
            if entity_type in ["DNA", "RNA", "PROTEIN"]:
                f2.write(f"{line.strip()}\t{entity_type}\n")


# ------------------------------------------------------------------------------#
# Function to compare the GILDA and CHEBI grounding results                     #
# ------------------------------------------------------------------------------#


def compare_grounding(chebi_file: str, gilda_file: str, intersection_file: str):
    """Compare ChEBI and GILDA grounding results.

        Generate intersection and difference files.

    Parameters
    ----------
    chebi_file (str): Path to the ChEBI grounding results TSV file
    gilda_file (str): Path to the GILDA grounding results TSV file
    intersection_file (str): Path to the output intersection TSV file
    """
    df_chebi = pd.read_csv(chebi_file, sep="\t")
    df_gilda = pd.read_csv(gilda_file, sep="\t")

    # Add a source column to track which database each row comes from
    df_chebi["Source"] = "CHEBI"
    df_gilda["Source"] = "GILDA"

    df_merged = df_chebi.merge(df_gilda, how="outer")
    df_merged.to_csv(intersection_file, sep="\t", index=False)


if __name__ == "__main__":
    # Grounding the molecule to PDB database
    logger.info("Starting molecule grounding from PDB...")
    grouding_mol_pdb("data/MOL.txt", "results/ground_mol_pdb.tsv")
    logger.success("Molecule grounding completed.")
    # Grounding the molecule to uniprot database
    logger.info("Starting molecule grounding from UniProt...")
    grouding_mol_uniprot("data/MOL.txt", "results/ground_mol_uniprot.tsv")
    logger.success("Molecule grounding completed.")
    # Grounding the molecule to sequence databases
    logger.info("Starting molecule grounding for sequences...")
    grounding_sequence("data/MOL.txt", "results/ground_mol_sequence.tsv")
    logger.success("Molecule grounding completed.")

    # Grounding the molecule to chebi database
    logger.info("Starting molecule grounding from Chebi...")
    grouding_mol_chebi("data/MOL.txt", "results/ground_mol_chebi.tsv")
    logger.success("Molecule grounding completed.")
    # Grounding the molecule with gilda
    logger.info("Starting Gilda grounding...")
    grounding_gilda("data/MOL.txt", "results/ground_mol_gilda.tsv")
    logger.success("Gilda grounding completed.")

    # Compare the grounding results from chebi and gilda
    logger.info("Comparing grounding results from ChEBI and GILDA...")
    compare_grounding(
        "results/ground_mol_chebi.tsv",
        "results/ground_mol_gilda.tsv",
        "results/ground_mol_comparison.tsv",
    )
    logger.success("Grounding comparison completed.")
