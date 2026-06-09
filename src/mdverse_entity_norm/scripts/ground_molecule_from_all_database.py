"""Script to normalize small molecule entities across various databases."""

import re
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger

API_KEGG = "https://rest.kegg.jp"
API_CHEBI = "https://www.ebi.ac.uk/chebi/backend/api/public/es_search/"
API_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
API_PDB = "https://data.rcsb.org/rest/v1/core/entry/"
API_UNIPROT = "https://rest.uniprot.org/uniprotkb/"


def get_type(entry: str) -> str:
    """Determine the molecular entity type based on regex pattern.

    Parameters
    ----------
    entry : str
        The molecular identifier string to classify.

    Returns
    -------
    str
        The entity type: "PDB", "UNIPROT", "DNA", "RNA", "PROTEIN",
        or "SMALL_MOLECULE" for anything else.
    """
    entry = entry.replace("`", "'")
    entry = entry.replace("\u2019", "'")
    logger.info(entry)

    # PDB codes are 4 characters starting with a number
    if re.search(r"^[1-9]([a-z]|[1-9]){3}$", entry) is not None:
        return "PDB"

    # UniProt accession pattern matching
    if (
        re.search(
            r"[opq][0-9][a-z0-9]{3}[0-9]|[a-nr-z][0-9]([a-z][a-z0-9]{2}[0-9]){1,2}",
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

    # Amino acid sequence pattern
    if (
        re.search(
            r"^(?![ACGT]+$)(?=.*[FWY])(?=.*[KRH])[ACDEFGHIKLMNPQRSTVWY]{20,}$", entry
        )
        is not None
        and len(entry) > 4
    ):
        return "PROTEIN"

    return "SMALL_MOLECULE"


def call_pdb(code_pdb: str) -> dict:
    """Query the Protein Data Bank API for a given PDB code.

    Parameters
    ----------
    code_pdb : str
        4-character PDB identifier code.

    Returns
    -------
    dict
        Details retrieved from the PDB database (entry_id, pubmed_id, doi, name).
    """
    logger.info(f"Searching for `{code_pdb}` in PDB database...")
    response = httpx.get(f"{API_PDB}{code_pdb}", timeout=10)
    if response.status_code == 200:
        results = response.json()
        logger.success(f"PDB grounding successful for `{code_pdb}`.")
        return {
            "entity_name": code_pdb,
            "type": "PDB",
            "id": results.get("rcsb_id", "Not Available"),
            "name": results.get("struct", {}).get("title", "Not Available"),
        }
    else:
        logger.warning(
            f"Failed to ground `{code_pdb}` in PDB database (HTTP {response.status_code})."
        )
        return {
            "entity_name": code_pdb,
            "type": "PDB",
            "id": None,
            "name": None,
        }


def call_uniprot(code_uniprot: str) -> dict:
    """Query the UniProt API for a given UniProt accession code.

    Parameters
    ----------
    code_uniprot : str
        UniProt accession identifier.

    Returns
    -------
    dict
        Details retrieved from the UniProt database (accession, id, gene_name).
    """
    response = httpx.get(f"{API_UNIPROT}{code_uniprot}.json", timeout=10)
    if response.status_code == 200:
        results = response.json()
        logger.success(f"UniProt grounding successful for `{code_uniprot}`.")
        return {
            "entity_name": code_uniprot,
            "type": "UNIPROT",
            "id": results.get("primaryAccession"),
            "name": results.get("genes", [{}])[0].get("geneName", {}).get("value"),
        }
    else:
        logger.warning(
            f"Failed to ground `{code_uniprot}` in UniProt database (HTTP {response.status_code})."
        )
        return {
            "entity_name": code_uniprot,
            "type": "UNIPROT",
            "id": None,
            "name": None,
        }


def filter_molecules(molecules: list[str]) -> tuple[list[str], list[dict]]:
    """Split molecules into small molecules and other entity types.

    Small molecules are passed to the ChEBI/PubChem/KEGG pipeline.
    PDB, UNIPROT, DNA, RNA, PROTEIN entities are queried and saved separately.

    Parameters
    ----------
    molecules : list[str]
        The full list of molecule entity names.

    Returns
    -------
    tuple[list[str], list[dict]]
        - list of small molecule names to pass to the chemical pipeline
        - list of dicts for non-small-molecule entities (for TSV output)
    """
    small_molecules = []
    other_entities = []

    for mol in molecules:
        entity_type = get_type(mol)
        if entity_type == "SMALL_MOLECULE":
            small_molecules.append(mol)
        elif entity_type == "PDB":
            result = call_pdb(mol)
            other_entities.append(result)
        elif entity_type == "UNIPROT":
            result = call_uniprot(mol)
            other_entities.append(result)
        else:
            other_entities.append(
                {
                    "entity_name": mol,
                    "type": entity_type,
                    "id": None,
                    "name": None,
                }
            )

    logger.info(
        f"Filtered {len(small_molecules)} small molecules and {len(other_entities)} other entities."
    )
    return small_molecules, other_entities


def save_pdb_uniprot_seq_entities(
    other_entities: list[dict],
    output_file: Path,
) -> None:
    """Save PDB, UniProt, DNA, RNA, and PROTEIN entities in a TSV file.

    Parameters
    ----------
    other_entities : list[dict]
        List of dicts with keys: entity_name, type, id, name.
    output_file : Path
        The path to the output TSV file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as file:
        file.write("Molecule\tType\tID\tName\n")
        file.writelines(
            f"{entity['entity_name']}\t{entity['type']}\t{entity['id']}\t{entity['name']}\n"
            for entity in other_entities
        )

    logger.info(
        f"Saved {len(other_entities)} non-small-molecule entities to {output_file}."
    )


def query_kegg_by_name(
    entity_name: str,
) -> tuple[str, str] | tuple[None, None] | tuple[str, None] | tuple[None, str]:
    """Return the KEGG ID linked to the molecule name.

    Parameters
    ----------
    entity_name : str
        The name of the molecule to query.

    Returns
    -------
    tuple[str, str] | tuple[None, None] | tuple[str, None] | tuple[None, str]
        A tuple containing the pubchem ID and chebi ID returned by kegg.
    """
    kegg_response = httpx.get(f"{API_KEGG}/find/compound/{entity_name}", timeout=200)
    if kegg_response.status_code != 200:
        logger.warning(f"Failed to retrieve KEGG ID for {entity_name}")
        return None, None
    kegg_text = kegg_response.text.strip()
    if not kegg_text:
        logger.warning(f"No KEGG entry found for {entity_name}")
        return None, None
    kegg_id = kegg_text.split("\t")[0].strip()
    kegg_id = kegg_id.split(";")[0]

    pubchem_response = httpx.get(f"{API_KEGG}/conv/pubchem/cpd:{kegg_id}", timeout=200)
    if pubchem_response.status_code != 200:
        logger.warning(f"Failed to retrieve PubChem ID for {entity_name} from KEGG")
        return None, None
    pubchem_parts = pubchem_response.text.strip().split("\t")
    if len(pubchem_parts) < 2:
        logger.warning(f"No PubChem mapping in KEGG for {entity_name}")
        return None, None
    pubchem_id_from_kegg = pubchem_parts[1].replace("pubchem:", "").strip()

    chebi_response = httpx.get(f"{API_KEGG}/conv/chebi/cpd:{kegg_id}", timeout=200)
    if chebi_response.status_code != 200:
        logger.warning(f"Failed to retrieve CHEBI ID for {entity_name} from KEGG")
        return None, None
    chebi_parts = chebi_response.text.strip().split("\t")
    if len(chebi_parts) < 2:
        logger.warning(f"No ChEBI mapping in KEGG for {entity_name}")
        return pubchem_id_from_kegg, None
    chebi_id_from_kegg = chebi_parts[1].replace("chebi:", "").strip()

    return pubchem_id_from_kegg, chebi_id_from_kegg


def query_chebi_by_name(entity_name: str) -> str | None:
    """Return the CHEBI ID linked to the molecule name.

    Parameters
    ----------
    entity_name : str
        The name of the molecule to query.

    Returns
    -------
    str | None
        The CHEBI ID returned by CHEBI.
    """
    parameters = {"term": entity_name}
    chebi_response = httpx.get(f"{API_CHEBI}", params=parameters, timeout=200)
    if chebi_response.status_code == 200:
        results = chebi_response.json()["results"]
        if not results:
            logger.warning(f"No ChEBI entry found for {entity_name}")
            return None
        chebi_id = results[0]["_id"]
        return chebi_id
    else:
        logger.warning(f"Failed to retrieve CHEBI ID for {entity_name}")
        return None


def query_pubchem_by_name(entity_name: str) -> str | None:
    """Return the PubChem compound ID linked to the molecule name.

    Parameters
    ----------
    entity_name : str
        The name of the molecule to query.

    Returns
    -------
    str | None
        The PubChem compound ID returned by PubChem.
    """
    pubchem_response = httpx.get(
        f"{API_PUBCHEM}/compound/name/{entity_name}/JSON", timeout=200
    )
    if pubchem_response.status_code == 200:
        pubchem_id = str(pubchem_response.json()["PC_Compounds"][0]["id"]["id"]["cid"])
        return pubchem_id
    else:
        logger.warning(f"Failed to retrieve PubChem ID for {entity_name}")
        return None


def query_pubchem_by_substance(substance_id: str) -> str | None:
    """Return the PubChem compound ID linked to the substance ID.

    Parameters
    ----------
    substance_id : str
        The substance ID to query.

    Returns
    -------
    str | None
        The PubChem compound ID returned by PubChem.
    """
    pubchem_response = httpx.get(
        f"{API_PUBCHEM}/substance/sid/{substance_id}/cids/JSON", timeout=200
    )
    if pubchem_response.status_code == 200:
        compound_id = str(
            pubchem_response.json()["InformationList"]["Information"][0]["CID"]
        )
        return compound_id
    else:
        logger.warning(f"Failed to retrieve PubChem ID for {substance_id}")
        return None


def query_pubchem_substance_by_name(entity_name: str) -> str | None:
    """Return the PubChem substance ID linked to the molecule name.

    Parameters
    ----------
    entity_name : str
        The name of the molecule to query.

    Returns
    -------
    str | None
        The first PubChem substance ID found, or None.
    """
    response = httpx.get(
        f"{API_PUBCHEM}/substance/name/{entity_name}/JSON", timeout=200
    )
    if response.status_code != 200:
        logger.warning(f"Failed to retrieve PubChem substance for {entity_name}")
        return None
    substances = response.json().get("PC_Substances", [])
    if not substances:
        logger.warning(f"No PubChem substance found for {entity_name}")
        return None
    sid = substances[0].get("sid", {}).get("id")
    if sid is None:
        logger.warning(f"No SID found in PubChem substance response for {entity_name}")
        return None
    return str(sid)


def get_chebi_id_from_pubchem_synonyms(pubchem_id: str) -> str | None:
    """Return the CHEBI ID linked to the PubChem compound ID via synonyms.

    Parameters
    ----------
    pubchem_id : str
        The PubChem compound ID to query.

    Returns
    -------
    str | None
        The CHEBI ID found in PubChem synonyms.
    """
    pubchem_response = httpx.get(
        f"{API_PUBCHEM}/compound/cid/{pubchem_id}/synonyms/JSON", timeout=200
    )
    if pubchem_response.status_code == 200:
        synonyms = pubchem_response.json()["InformationList"]["Information"][0][
            "Synonym"
        ]
        for synonym in synonyms:
            if synonym.startswith("CHEBI:"):
                chebi_id = synonym.replace("CHEBI:", "")
                return chebi_id
        logger.warning(f"No CHEBI ID found in synonyms for PubChem ID {pubchem_id}")
        return None
    else:
        logger.warning(f"Failed to retrieve synonyms for PubChem ID {pubchem_id}")
        return None


def load_molecule_entities(file_path: Path) -> list:
    """Load molecular identifiers from a file into a list.

    Parameters
    ----------
    file_path : Path
        Path to the input file containing molecular identifiers.

    Returns
    -------
    list
        A list of molecular identifiers loaded from the file.
    """
    logger.info(f"Loading MOL entities from {file_path}...")
    entities = pd.read_csv(file_path, sep="\t")
    mol_entities = entities[entities["category"] == "MOL"]
    mol_entities = list(mol_entities["entity"].unique())
    molecule_liste = []
    for molecule in mol_entities:
        if len(molecule) > 3:
            molecule_liste.append(molecule)
    molecule_liste = list(set(molecule_liste))
    logger.info(f"Loaded {len(molecule_liste)} MOL entities successfully.")
    return molecule_liste


def compare_chebi_ids(
    chebi_id: str | None,
    chebi_id_from_kegg: str | None,
    chebi_id_from_pubchem: str | None,
    mol: str,
) -> bool:
    """Compare CHEBI IDs from ChEBI, KEGG and PubChem.

    Parameters
    ----------
    chebi_id : str | None
        The CHEBI ID retrieved directly from ChEBI.
    chebi_id_from_kegg : str | None
        The CHEBI ID retrieved via KEGG.
    chebi_id_from_pubchem : str | None
        The CHEBI ID retrieved via PubChem synonyms.
    mol : str
        The molecule entity name (used for logging).

    Returns
    -------
    bool
        True if at least 2 CHEBI IDs match, False otherwise.
    """
    if (
        (
            chebi_id is not None
            and chebi_id_from_pubchem is not None
            and chebi_id == chebi_id_from_pubchem
        )
        or (
            chebi_id is not None
            and chebi_id_from_kegg is not None
            and chebi_id == chebi_id_from_kegg
        )
        or (
            chebi_id_from_pubchem is not None
            and chebi_id_from_kegg is not None
            and chebi_id_from_pubchem == chebi_id_from_kegg
        )
    ):
        logger.info(f"CHEBI ID for {mol} is the same in at least 2 databases.")
        return True
    logger.warning(f"CHEBI ID for {mol} is different across databases.")
    return False


def save_chebi_comparaison_in_tsv(
    molecules: list[str],
    output_file: Path,
) -> None:
    """Save the CHEBI ID comparison results in a TSV file.

    Parameters
    ----------
    molecules : list[str]
        The list of molecule entity names.
    output_file : Path
        The path to the output TSV file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(
            "Molecule\tCHEBI_ID\tCHEBI_ID_from_KEGG\tCHEBI_ID_from_PubChem\tMatch\n"
        )

        for index, mol in enumerate(molecules, start=1):
            logger.info("=" * 50)
            logger.info(f"Processing molecule {index}/{len(molecules)}: '{mol}'")

            chebi_id = query_chebi_by_name(mol)
            logger.info(f"  → CHEBI_ID direct: '{chebi_id}'")

            pubchem_id = query_pubchem_by_name(mol)
            logger.info(f"  → PubChem_ID direct: '{pubchem_id}'")

            chebi_id_from_pubchem = None
            if pubchem_id is not None and len(pubchem_id) > 0:
                chebi_id_from_pubchem = get_chebi_id_from_pubchem_synonyms(pubchem_id)
                logger.info(
                    f"  → CHEBI_ID via PubChem ({pubchem_id}): '{chebi_id_from_pubchem}'"
                )
            else:
                # Fallback : pas de CID mais peut-être un SID avec un ChEBI dans ses synonymes
                logger.warning(
                    f"  → Pas de PubChem CID pour {mol}, tentative via SID substance..."
                )
                sid = query_pubchem_substance_by_name(mol)
                if sid is not None and len(sid) > 0:
                    chebi_id_from_pubchem = get_chebi_id_from_pubchem_synonyms_from_sid(
                        sid
                    )
                    logger.info(
                        f"  → CHEBI_ID via SID ({sid}): '{chebi_id_from_pubchem}'"
                    )
                else:
                    logger.warning(f"  → Pas de SID PubChem non plus pour {mol}")

            pubchem_id_from_kegg, chebi_id_from_kegg = query_kegg_by_name(mol)
            logger.info(f"  → PubChem_ID via KEGG: '{pubchem_id_from_kegg}'")
            logger.info(f"  → CHEBI_ID via KEGG: '{chebi_id_from_kegg}'")

            if pubchem_id_from_kegg is not None and pubchem_id_from_kegg != pubchem_id:
                logger.info(
                    "  → PubChem KEGG différent du direct, recherche de CHEBI via ce nouveau PubChem..."
                )
                chebi_id_from_kegg_via_pubchem = get_chebi_id_from_pubchem_synonyms(
                    pubchem_id_from_kegg
                )
                logger.info(
                    f"  → CHEBI via PubChem KEGG: '{chebi_id_from_kegg_via_pubchem}'"
                )
                if chebi_id_from_kegg_via_pubchem is not None:
                    chebi_id_from_kegg = chebi_id_from_kegg_via_pubchem

            match = compare_chebi_ids(
                chebi_id, chebi_id_from_kegg, chebi_id_from_pubchem, mol
            )
            logger.info(f"  → Match (au moins 2 IDs identiques): {match}")

            line = f"{mol}\t{chebi_id}\t{chebi_id_from_kegg}\t{chebi_id_from_pubchem}\t{match}\n"
            file.write(line)
            logger.info(f"  → Ligne écrite: {line.strip()}")

    logger.info("=" * 50)
    logger.info(f"Fichier sauvegardé: {output_file}")

    logger.info("Aperçu du fichier généré:")
    with open(output_file, encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines[:10]):
            logger.info(f"  Ligne {i}: {line.strip()}")


def compare_pubchem_ids(
    pubchem_id: str | None,
    pubchem_id_from_kegg: str | None,
    mol: str,
) -> bool:
    """Compare PubChem IDs from direct query and KEGG.

    Parameters
    ----------
    pubchem_id : str | None
        The PubChem ID retrieved directly from PubChem.
    pubchem_id_from_kegg : str | None
        The PubChem ID retrieved via KEGG.
    mol : str
        The molecule entity name (used for logging).

    Returns
    -------
    bool
        True if the PubChem IDs match, False otherwise.
    """
    if pubchem_id is None or pubchem_id_from_kegg is None:
        logger.warning(f"PubChem ID missing for {mol}, cannot compare.")
        return False

    if pubchem_id == pubchem_id_from_kegg:
        logger.info(f"PubChem ID for {mol} matches directly.")
        return True

    pubchem_id_from_kegg_compound = get_compound_id_from_kegg_substance(
        pubchem_id_from_kegg
    )
    if (
        pubchem_id_from_kegg_compound is not None
        and pubchem_id_from_kegg_compound == pubchem_id
    ):
        logger.info(f"PubChem ID for {mol} matches after resolving KEGG substance.")
        return True

    logger.warning(f"PubChem ID for {mol} does not match across sources.")
    return False


def get_chebi_id_from_pubchem_synonyms_from_sid(sid: str) -> str | None:
    """Return the CHEBI ID found in the synonyms of a PubChem substance SID.

    Parameters
    ----------
    sid : str
        The PubChem substance ID to query.

    Returns
    -------
    str | None
        The CHEBI ID found in the substance synonyms, or None.
    """
    response = httpx.get(f"{API_PUBCHEM}/substance/sid/{sid}/JSON", timeout=200)
    if response.status_code != 200:
        logger.warning(f"Failed to retrieve substance data for SID {sid}")
        return None
    substances = response.json().get("PC_Substances", [])
    for substance in substances:
        if substance.get("sid", {}).get("id") == int(sid):
            synonyms = substance.get("synonyms", [])
            for synonym in synonyms:
                if synonym.startswith("CHEBI:"):
                    chebi_id = synonym.replace("CHEBI:", "")
                    return chebi_id
            logger.warning(f"No CHEBI ID found in synonyms for SID {sid}")
            return None
    logger.warning(f"SID {sid} not found in PubChem response")
    return None


def get_pubchem_cid_from_substance(sid: str) -> str | None:
    """Return the PubChem compound ID linked to a substance ID by looking at the compound field.

    Parameters
    ----------
    sid : str
        The PubChem substance ID to query.

    Returns
    -------
    str | None
        The PubChem compound ID found in the substance's compound field.
    """
    response = httpx.get(f"{API_PUBCHEM}/substance/sid/{sid}/JSON", timeout=200)
    if response.status_code != 200:
        logger.warning(f"Failed to retrieve substance data for SID {sid}")
        return None

    substances = response.json().get("PC_Substances", [])
    for substance in substances:
        if substance.get("sid", {}).get("id") == int(sid):
            compound_list = substance.get("compound", [])
            for entry in compound_list:
                cid = entry.get("id", {}).get("id", {}).get("cid")
                if cid is not None:
                    return str(cid)
            logger.warning(f"No CID found in compound field for SID {sid}")
            return None

    logger.warning(f"SID {sid} not found in PubChem response")
    return None


def get_synonym_from_pubchem_substance(sid: str) -> str | None:
    """Return the first synonym of a PubChem substance.

    Parameters
    ----------
    sid : str
        The PubChem substance ID to query.

    Returns
    -------
    str | None
        The first synonym found for the substance.
    """
    response = httpx.get(f"{API_PUBCHEM}/substance/sid/{sid}/JSON", timeout=200)
    if response.status_code != 200:
        logger.warning(f"Failed to retrieve substance data for SID {sid}")
        return None

    substances = response.json().get("PC_Substances", [])
    for substance in substances:
        if substance.get("sid", {}).get("id") == int(sid):
            synonyms = substance.get("synonyms", [])
            if not synonyms:
                logger.warning(f"No synonyms found for SID {sid}")
                return None
            return synonyms[0]

    logger.warning(f"SID {sid} not found in PubChem response")
    return None


def get_compound_id_from_kegg_substance(sid: str) -> str | None:
    """Return the PubChem compound ID from a KEGG substance SID using a cascade of fallbacks.

    First tries to find a CID directly in the substance's compound field.
    If not found, tries the direct SID to CID mapping via query_pubchem_by_substance.
    If still not found, takes the first synonym and searches PubChem compound by name.

    Parameters
    ----------
    sid : str
        The PubChem substance ID retrieved from KEGG.

    Returns
    -------
    str | None
        The PubChem compound ID found, or None if all methods fail.
    """
    cid = get_pubchem_cid_from_substance(sid)
    if cid is not None:
        logger.info(f"CID {cid} found in compound field for SID {sid}")
        return cid

    cid = query_pubchem_by_substance(sid)
    if cid is not None:
        logger.info(f"CID {cid} found via direct SID mapping for SID {sid}")
        return cid

    synonym = get_synonym_from_pubchem_substance(sid)
    if synonym is None:
        logger.warning(f"No fallback possible for SID {sid}")
        return None
    logger.info(f"Trying first synonym '{synonym}' for SID {sid}")
    cid = query_pubchem_by_name(synonym)
    if cid is not None:
        logger.info(f"CID {cid} found via synonym '{synonym}' for SID {sid}")
        return cid

    logger.warning(f"All methods failed to find a CID for SID {sid}")
    return None


def get_no_chebi_match(chebi_comparaison_file: Path) -> list[str]:
    """Extract molecule names with no CHEBI ID match from the comparison file.

    Parameters
    ----------
    chebi_comparaison_file : Path
        The path to the CHEBI comparison TSV file.

    Returns
    -------
    list[str]
        A list of molecule names that have no CHEBI ID match across databases.
    """
    df = pd.read_csv(chebi_comparaison_file, sep="\t")
    no_match_df = df[df["Match"] == False]
    return no_match_df["Molecule"].tolist()


def save_pubchem_comparaison_in_tsv(
    molecules: list[str],
    output_file: Path,
) -> None:
    """Save the PubChem ID comparison results in a TSV file.

    Parameters
    ----------
    molecules : list[str]
        The list of molecule entity names.
    output_file : Path
        The path to the output TSV file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as file:
        file.write("Molecule\tPubChem_ID\tPubChem_ID_from_KEGG\tMatch\n")
        for index, mol in enumerate(molecules, start=1):
            logger.info(f"Processing molecule {index}/{len(molecules)}: {mol}")
            pubchem_id = query_pubchem_by_name(mol)
            pubchem_id_from_kegg, _ = query_kegg_by_name(mol)

            match = compare_pubchem_ids(pubchem_id, pubchem_id_from_kegg, mol)

            file.write(f"{mol}\t{pubchem_id}\t{pubchem_id_from_kegg}\t{match}\n")


if __name__ == "__main__":
    entities_file = Path("data/entities.tsv")
    output_dir = Path("results/ground_molecule/same_grounding_mol")

    all_molecules = load_molecule_entities(entities_file)

    small_molecules, other_entities = filter_molecules(all_molecules)

    save_pdb_uniprot_seq_entities(
        other_entities=other_entities,
        output_file=output_dir / "pdb_uniprot_seq_entities.tsv",
    )

    chebi_output = output_dir / "chebi_comparaison.tsv"
    save_chebi_comparaison_in_tsv(
        molecules=small_molecules,
        output_file=chebi_output,
    )

    # # Pipeline PubChem pour les molécules sans match ChEBI
    # no_chebi_match_molecules = get_no_chebi_match(chebi_output)
    # logger.info(
    #     f"Number of molecules with no CHEBI ID match: {len(no_chebi_match_molecules)}"
    # )
    # logger.info("Saving PubChem comparison for molecules with no CHEBI match...")
    # save_pubchem_comparaison_in_tsv(
    #     molecules=no_chebi_match_molecules,
    #     output_file=output_dir / "pubchem_comparaison_no_chebi_match.tsv",
    # )
