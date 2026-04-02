"""Module for using regex, sending requests and grounding.

re :This module provides regular expression matching operations.
requests : This module allows you to send HTTP/ requests.
gilda : This module allows Grounding Integrating Learned Disambiguation.
"""

import json
import os
import re
import sys
from datetime import UTC, datetime

import gilda
import httpx
import pandas as pd
from loguru import logger

# API endpoints for different molecular databases
API_PDB = "https://data.rcsb.org/rest/v1/core/entry/"
API_UNIPROT = "https://rest.uniprot.org/uniprotkb/"
API_CHEBI = "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"
API_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def load_molecule(filename: str):
    """Load molecular identifiers from a file into a list.

    Parameters
    ----------
    filename (str): Path to the input file containing molecular identifiers

    Returns
    -------
    list: A list of molecular identifiers loaded from the file
    """
    results = []

    with open(filename) as raw_molecule_file:
        logger.info("Transforming the file into a list")
        for line in raw_molecule_file:
            results.append(line.strip())
    return results


def get_type(entry: str):
    """Determine the molecular entity type based on regex pattern.

    Parameters
    ----------
    entry (str): The molecular identifier string to classify

    Returns
    -------
    str: The entity type ("PDB", "UNIPROT", "DNA", "RNA", or "CHEBI")
    """
    entry = entry.replace(
        "`", "'"
    )  # Replace backticks with single quotes for sequence patterns
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
    # [WIP : need another logic to avoid grounding Chebi entities as proteins]
    if re.search(r"^(?!^[agct]+$)[acdefghiklmnpqrstvwy]+$", entry) is not None:
        return "PROTEIN"
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
        logger.info(
            f"From PDB {code_pdb}: for {code_pdb} -> Status HTTP : {response.status_code}"
            f"(The request succeeded`)"
        )
        results = response.json()

        result_dict = {
            "pubmed_id": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_pub_med", "Not Available"
            ),
            "doi": results.get("rcsb_primary_citation", {}).get(
                "pdbx_database_id_doi", "Not Available"
            ),
            "title": results.get("struct", {}).get("title", "Not Available"),
            "rcsb_id": results.get("rcsb_id", "Not Available"),
        }
    else:
        result_dict = {code_pdb: response.status_code}
        logger.warning(
            f"From PDB: for {code_pdb} -> Status HTTP : {response.status_code}"
            f"(The server can't process your request`)"
        )
    return result_dict


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
        logger.info(
            f"from UniProt: for {code_uniprot} : -> Status HTTP : {response.status_code}"
            f"(The request succeeded`)"
        )
        results = response.json()

        result_dict = {
            "accession": results.get("primaryAccession"),
            "uniprot_id": results.get("uniProtkbId"),
            "gene_name": results.get("genes", [{}])[0].get("geneName", {}).get("value"),
        }
    else:
        logger.warning(
            f"from UniProt: for {code_uniprot} : -> Status HTTP : {response.status_code}"
            f"(The server can't process your request)"
        )
        result_dict = {code_uniprot: response.status_code}
    return result_dict


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
            f"from ChEBI: for {entity_name} : -> Status HTTP : {response.status_code} "
            f"(The request succeeded)"
        )
        results = response.json()["results"][0]

        result_dict = {
            "id": results.get("_id", "Not Available"),
            "score": results.get("_score", "Not Available"),
            "name": results.get("_source", {}).get("ascii_name", "Not Available"),
            "star": results.get("_source", {}).get("stars", "Not Available"),
            "nb_res": json.loads(string_response)["total"],
        }
    else:
        logger.warning(
            f"from ChEBI: for {entity_name} : -> Status HTTP : {response.status_code}"
            f"(The server can't process your request)"
        )
        result_dict = {entity_name: response.status_code}
    return result_dict


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
            f"Using Gilda : for `{entity_name}` : From {grounding_res['term']['db']}"
            f"Grounding in progress..."
        )

        result_dict = {
            "db": grounding_res.get("term", {}).get("db", "Not Available"),
            "id": grounding_res.get("term", {})
            .get("id", "Not Available")
            .strip("CHEBI:"),
            "score": grounding_res.get("score", "Not Available"),
            "name": grounding_res.get("term", {}).get("text", "Not Available"),
            "url": grounding_res.get("url", "Not Available"),
            "nb_res": len(results),
        }
    else:
        logger.warning(
            f"Using Gilda : for `{entity_name}` : No grounding results found."
        )
        result_dict = {entity_name: "Not found by Gilda"}
    return result_dict


def call_pubchem(entity_name: str):
    """Query the PubChem API for a given molecule name.

    Parameters
    ----------
    entity_name (str): name of the compound

    Returns
    -------
    dict : Details retrieved from PubChem (cid, full_name)
    """
    response = httpx.get(
        f"{API_PUBCHEM}/compound/name/{entity_name}/property/IUPACName,MolecularFormula/JSON",
        timeout=10,
    )
    if response.status_code == 200:
        logger.debug(
            f"from PubChem: for {entity_name} : -> Status HTTP : {response.status_code} "
            f"(The request succeeded)"
        )
        results = response.json()["PropertyTable"]["Properties"][0]
        if results:
            result_dict = {
                "cid": results.get("CID", "Not Available"),
                "full_name": results.get("IUPACName", "Not Available"),
                "molecular_formula": results.get("MolecularFormula", "Not Available"),
            }
    else:
        logger.warning(
            f"from PubChem: for {entity_name} : -> Status HTTP : {response.status_code}"
            f"(The server can't process your request)"
        )
        result_dict = {entity_name: response.status_code}
    return result_dict


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
                if result:
                    f2.write(
                        f"{line.strip()}\t{entity_type}\tCHEBI\t{result['id']}\t{result['score']}\t{result['name']}\t{result['star']}\t{result['nb_res']}\n"
                    )
                else:
                    entity_type = "PubChem"
                    result = call_pubchem(line.strip())
                    if result is not None:
                        f2.write(
                            f"{line.strip()}\t{entity_type}\tPubChem\t{result['cid']}\t"
                            f"Not Available\t{result['full_name']}\t"
                            f"Not Available\tNot Available\n"
                        )
                    else:
                        f2.write(
                            f"{line.strip()}\t{entity_type}\tPubChem\tNOT_FOUND\t"
                            f"Not Available\tNOT_AVAILABLE\tNot Available\tNot Available\n"
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
                    entity_type = "PubChem"
                    result = call_pubchem(line.strip())
                    if result is not None:
                        f2.write(
                            f"{line.strip()}\t{entity_type}\tPubChem\t{result['cid']}\t"
                            f"Not Available\t{result['full_name']}\t"
                            f"Not Available\tNot Available\n"
                        )
                    else:
                        f2.write(
                            f"{line.strip()}\t{entity_type}\tPubChem\tNOT_FOUND\t"
                            f"Not Available\tNOT_AVAILABLE\tNot Available\tNot Available\n"
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


def diff_grounding(chebi_filename: str, gilda_filename: str, diff_file: str):
    """Generate a file containing the differences between ChEBI and GILDA grounding results.

    Parameters
    ----------
    chebi_filename (str): Path to the ChEBI grounding results TSV file
    gilda_filename (str): Path to the GILDA grounding results TSV file
    diff_file (str): Path to the output difference TSV file

    Returns
    -------
    dataFrame: Result dataframe containing the
    """
    df_chebi = pd.read_csv(chebi_filename, sep="\t")
    df_gilda = pd.read_csv(gilda_filename, sep="\t")

    df_merged = df_chebi.merge(df_gilda, how="outer")
    df_merged = df_merged.drop("Type", axis=1)
    df_merged = df_merged.drop("URL", axis=1)
    df_merged = df_merged.drop("Stars", axis=1)
    df_merged = df_merged.iloc[:, [0, 6, 1, 2, 4, 3, 5]]

    return df_merged


if __name__ == "__main__":
    # Grounding the molecule to PDB database
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    logger.add(
        sys.stderr,
        level="DEBUG",
    )
    os.makedirs("logs", exist_ok=True)
    logger.add(
        f"logs/ground_molecule_{timestamp}.log",
        level="DEBUG",
    )
    # logger.info("Starting molecule grounding from PDB...")
    # grouding_mol_pdb("data/MOL.txt", "results/ground_mol_pdb.tsv")
    # logger.success("Molecule grounding completed.")
    # # Grounding the molecule to uniprot database
    # logger.info("Starting molecule grounding from UniProt...")
    # grouding_mol_uniprot("data/MOL.txt", "results/ground_mol_uniprot.tsv")
    # logger.success("Molecule grounding completed.")

    # Grounding the molecule to chebi database
    logger.info("Starting molecule grounding from Chebi...")
    grouding_mol_chebi("data/MOL.txt", "results/ground_mol_chebi.tsv")
    logger.success("Molecule grounding completed.")
    # # Grounding the molecule with gilda
    # logger.info("Starting Gilda grounding...")
    # grounding_gilda("data/MOL.txt", "results/ground_mol_gilda.tsv")
    # logger.success("Gilda grounding completed.")

    # # Grounding the molecule to sequence databases
    # logger.info("Starting molecule grounding for sequences...")
    # grounding_sequence("data/MOL.txt", "results/ground_mol_sequence.tsv")
    # logger.success("Molecule grounding completed.")

    # Compare the grounding results from chebi and gilda
    # logger.info("Comparing grounding results from ChEBI and GILDA...")
    # compare_grounding(
    #     "results/ground_mol_chebi.tsv",
    #     "results/ground_mol_gilda.tsv",
    #     "results/ground_mol_comparison.tsv",
    # )
    # logger.success("Grounding comparison completed.")
