"""Script to build a molecule grounding knowledge graph from normalization results."""

import networkx as nx
import pandas as pd
from loguru import logger
from pyvis.network import Network

COLOR_DATASET = "#FFD700"
COLOR_RAW_MOLECULE = "#4DA6FF"
COLOR_NORMALIZED = "#ff9999"


def get_molecules(
    chebi_file: str,
    pubchem_file: str,
    pdb_file: str,
) -> list[str]:
    """Return the list of molecule names that were successfully normalized.

    A molecule is considered normalized if it meets one of the following criteria:
    - In the ChEBI and PubChem file: Match == True
    - In the PDB file: the molecule has a non-null ID

    Parameters
    ----------
    chebi_file:
        Path to the ChEBI comparison TSV file (chebi_comparaison.tsv).
    pubchem_file:
        Path to the PubChem comparison TSV file (pubchem_comparaison_no_chebi_match.tsv).
    pdb_file:
        Path to the PDB/UniProt sequence entities TSV file (pdb_uniprot_seq_entities.tsv).

    Returns
    -------
    list[str]
        Deduplicated list of molecule names that were successfully normalized.
    """
    chebi_df = pd.read_csv(chebi_file, sep="\t")
    pubchem_df = pd.read_csv(pubchem_file, sep="\t")
    pdb_df = pd.read_csv(pdb_file, sep="\t")

    all_normalized = []

    for val_match, val_mol in zip(chebi_df["Match"], chebi_df["Molecule"], strict=True):
        if val_match and val_mol not in all_normalized:
            all_normalized.append(val_mol)

    for val_match, val_mol in zip(
        pubchem_df["Match"], pubchem_df["Molecule"], strict=True
    ):
        if val_match and val_mol not in all_normalized:
            all_normalized.append(val_mol)

    for val_id, val_mol in zip(pdb_df["ID"], pdb_df["Molecule"], strict=True):
        if pd.notna(val_id) and val_mol not in all_normalized:
            all_normalized.append(val_mol)
    return all_normalized


def get_json_files(entities_file: str, normalized_molecules: list[str]) -> list[str]:
    """Return the list of JSON files that contain at least one normalized molecule.

    Reads the entities TSV and filters for MOL-category rows whose entity name
    matches one of the normalized molecules. Returns the unique JSON file names
    associated with those rows.

    Parameters
    ----------
    entities_file:
        Path to the entities TSV file (entities.tsv).
    normalized_molecules:
        List of normalized molecule names, as returned by get_molecules().

    Returns
    -------
    list[str]
        Deduplicated list of JSON file names containing normalized molecules.
    """
    entities_df = pd.read_csv(entities_file, sep="\t")

    mol_entities = entities_df[entities_df["category"] == "MOL"]
    matching_rows = mol_entities[mol_entities["entity"].isin(normalized_molecules)]

    json_files = matching_rows["json_file"].dropna().unique().tolist()
    return json_files


def create_molecule_dataset_relationships(
    entities_file: str,
    chebi_file: str,
    pubchem_file: str,
    pdb_file: str,
) -> dict[str, list[str]]:
    """Return a mapping from each JSON dataset file to its normalized molecules.

    For each JSON file that contains at least one normalized molecule, the
    dictionary maps the file name to the list of normalized molecule names
    found in it.

    Parameters
    ----------
    entities_file:
        Path to the entities TSV file (entities.tsv).
    chebi_file:
        Path to the ChEBI comparison TSV file.
    pubchem_file:
        Path to the PubChem comparison TSV file.
    pdb_file:
        Path to the PDB/UniProt sequence entities TSV file.

    Returns
    -------
    dict[str, list[str]]
        Dictionary with JSON file names as keys and lists of normalized
        molecule names as values.
    """
    normalized_molecules = get_molecules(chebi_file, pubchem_file, pdb_file)

    entities_df = pd.read_csv(entities_file, sep="\t")
    mol_entities = entities_df[entities_df["category"] == "MOL"]
    matching_rows = mol_entities[mol_entities["entity"].isin(normalized_molecules)]

    dataset_to_molecules: dict[str, list[str]] = {}
    for _, row in matching_rows.iterrows():
        json_file = row["json_file"]
        molecule = row["entity"]
        if json_file not in dataset_to_molecules:
            dataset_to_molecules[json_file] = []
        if molecule not in dataset_to_molecules[json_file]:
            dataset_to_molecules[json_file].append(molecule)

    return dataset_to_molecules


def get_normalized_molecule_ids(
    chebi_file: str,
    pubchem_file: str,
    pdb_file: str,
) -> list[dict]:
    """Return a list of records with each normalized molecule name and its database ID.

    For ChEBI and PubChem, only rows where Match == True are included.
    For PDB, only rows with a non-null ID are included.
    Each record contains the source database, the original molecule name, and the ID.

    Parameters
    ----------
    chebi_file:
        Path to the ChEBI comparison TSV file.
    pubchem_file:
        Path to the PubChem comparison TSV file.
    pdb_file:
        Path to the PDB/UniProt sequence entities TSV file.

    Returns
    -------
    list[dict]
        List of dicts with keys: "molecule", "database", "id".
    """
    chebi_df = pd.read_csv(chebi_file, sep="\t")
    pubchem_df = pd.read_csv(pubchem_file, sep="\t")
    pdb_df = pd.read_csv(pdb_file, sep="\t")

    normalized_ids = []

    for _, row in chebi_df[chebi_df["Match"]].iterrows():
        chebi_id = (
            row["CHEBI_ID"]
            if pd.notna(row["CHEBI_ID"])
            else row.get("CHEBI_ID_from_KEGG") or row.get("CHEBI_ID_from_PubChem")
        )
        normalized_ids.append(
            {
                "molecule": row["Molecule"],
                "database": "ChEBI",
                "id": chebi_id,
            }
        )

    for _, row in pubchem_df[pubchem_df["Match"]].iterrows():
        pubchem_id = (
            row["PubChem_ID"]
            if pd.notna(row["PubChem_ID"])
            else row.get("PubChem_ID_from_KEGG")
        )
        normalized_ids.append(
            {
                "molecule": row["Molecule"],
                "database": "PubChem",
                "id": pubchem_id,
            }
        )

    for _, row in pdb_df[pdb_df["ID"].notna()].iterrows():
        normalized_ids.append(
            {
                "molecule": row["Molecule"],
                "database": "PDB",
                "id": row["ID"],
            }
        )

    return normalized_ids


def create_mol_normalisation_relationships(
    chebi_file: str,
    pubchem_file: str,
    pdb_file: str,
) -> dict[str, str]:
    """Return a mapping from raw molecule names to their normalized database IDs.

    Only molecules with Match == True (ChEBI, PubChem) or a non-null ID (PDB)
    are included. The normalized ID is formatted as "<DATABASE>:<ID>" for clarity
    (e.g., "CHEBI:15422", "PubChem:5793", "PDB:4HKR").

    Parameters
    ----------
    chebi_file:
        Path to the ChEBI comparison TSV file.
    pubchem_file:
        Path to the PubChem comparison TSV file.
    pdb_file:
        Path to the PDB/UniProt sequence entities TSV file.

    Returns
    -------
    dict[str, str]
        Dictionary mapping raw molecule names (e.g., "popc") to their
        normalized ID string (e.g., "CHEBI:16247").
    """
    normalized_records = get_normalized_molecule_ids(chebi_file, pubchem_file, pdb_file)

    mol_to_normalized_id: dict[str, str] = {}
    for record in normalized_records:
        molecule_name = record["molecule"]
        database = record["database"]
        db_id = record["id"]
        mol_to_normalized_id[molecule_name] = f"{database}:{db_id}"

    return mol_to_normalized_id


def create_knowledge_graph(
    entities_file: str,
    chebi_file: str,
    pubchem_file: str,
    pdb_file: str,
    normalized: bool = False,
) -> nx.Graph:
    """Build and return a NetworkX knowledge graph for molecule grounding.

    The graph always contains two layers of nodes and edges:
    - **Dataset nodes** (gold): one node per JSON file that contains at least
      one successfully normalised molecule.
    - **Raw molecule nodes** (blue): one node per molecule name as it appears
      in the entities TSV.
    - **Dataset → raw molecule edges**: drawn from create_molecule_dataset_relationships().

    When ``normalized`` is True, a third layer is added:
    - **Normalised ID nodes** (green): one node per unique normalised ID string
      (e.g. ``"CHEBI:45296"``), labelled with that ID.
    - **Raw molecule → normalised ID edges**: drawn from
      create_mol_normalisation_relationships().

    Parameters
    ----------
    entities_file:
        Path to the entities TSV file (entities.tsv).
    chebi_file:
        Path to the ChEBI comparison TSV file.
    pubchem_file:
        Path to the PubChem comparison TSV file.
    pdb_file:
        Path to the PDB/UniProt sequence entities TSV file.
    normalized:
        If False (default), return the raw graph (datasets + raw molecule names).
        If True, also attach normalised ID nodes and edges.

    Returns
    -------
    nx.Graph
        A NetworkX graph whose nodes carry ``"color"`` and ``"label"``
        attributes consumed by visualize_knowledge_graph().
    """
    graph = nx.Graph()
    dataset_to_molecules = create_molecule_dataset_relationships(
        entities_file, chebi_file, pubchem_file, pdb_file
    )

    for dataset_name, raw_molecules in dataset_to_molecules.items():
        graph.add_node(
            dataset_name, color=COLOR_DATASET, label=dataset_name, node_type="dataset"
        )

        for raw_molecule in raw_molecules:
            graph.add_node(
                raw_molecule,
                color=COLOR_RAW_MOLECULE,
                label=raw_molecule,
                node_type="raw_molecule",
            )
            graph.add_edge(dataset_name, raw_molecule)

    if normalized:
        mol_to_normalized_id = create_mol_normalisation_relationships(
            chebi_file, pubchem_file, pdb_file
        )

        for raw_molecule, normalized_id in mol_to_normalized_id.items():
            if raw_molecule not in graph:
                continue

            if normalized_id not in graph:
                graph.add_node(
                    normalized_id,
                    color=COLOR_NORMALIZED,
                    label=normalized_id,
                    node_type="normalized_id",
                )
            graph.add_edge(raw_molecule, normalized_id)

    return graph


def visualize_knowledge_graph(graph: nx.Graph, output_path: str) -> None:
    """Render the knowledge graph as an interactive HTML file using PyVis.

    Node colours follow the convention set in create_knowledge_graph():
    - Gold  (#FFD700): dataset (JSON file) nodes — displayed larger.
    - Blue  (#4DA6FF): raw molecule name nodes.
    - Green (#90EE90): normalised ID nodes (only present when normalized=True).

    All edges are drawn in gold with a uniform width. The physics layout uses
    repulsion to spread nodes apart with low central gravity, mimicking the
    style of the original graph.

    Parameters
    ----------
    graph:
        A NetworkX graph as returned by create_knowledge_graph().
    output_path:
        File path for the output HTML file (e.g. ``"graph.html"``).
    """
    net = Network(
        height="900px",
        width="100%",
        bgcolor="#f8f8f8",
        font_color="black",
    )
    net.from_nx(graph)

    net.repulsion(
        node_distance=250,
        central_gravity=0.00,
        spring_length=200,
        spring_strength=0.1,
        damping=1,
    )

    for edge in net.edges:
        edge["width"] = 3
        edge["color"] = "#c9a500"

    for node in net.nodes:
        node_color = node.get("color", "")

        if node_color == COLOR_DATASET:
            node["size"] = 40
        elif node_color == COLOR_NORMALIZED:
            node["size"] = 38
        else:
            node["size"] = 38

        node["font"] = {
            "size": 28,
            "face": "Arial",
            "color": "black",
        }

    net.write_html(output_path)


def main() -> None:
    """Run the full molecule grounding knowledge graph pipeline.

    Steps:
    1. Get all successfully normalised molecule names.
    2. Get the JSON dataset files that contain those molecules.
    3. Build the dataset → molecule relationship dictionary.
    4. Get the normalised molecule IDs (ChEBI / PubChem / PDB).
    5. Build the raw molecule → normalised ID relationship dictionary.
    6. Build and export the raw knowledge graph (no normalised IDs).
    7. Build and export the normalised knowledge graph (with normalised IDs).
    """
    chebi_file = "results/ground_molecule/same_grounding_mol/chebi_comparaison.tsv"
    pubchem_file = "results/ground_molecule/same_grounding_mol/pubchem_comparaison_no_chebi_match.tsv"
    pdb_file = "results/ground_molecule/same_grounding_mol/pdb_uniprot_seq_entities.tsv"
    entities_files = "/data/zenati/mdverse_entity_norm/data/entities.tsv"

    non_normalized_knowledge_graph = (
        "results/ground_molecule/molecule_graph/graph_raw.html"
    )
    normalized_knowledge_graph = (
        "results/ground_molecule/molecule_graph/graph_normalized.html"
    )
    logger.info("Get normalised molecules")
    normalized_molecules = get_molecules(chebi_file, pubchem_file, pdb_file)
    logger.info(f"  {len(normalized_molecules)} normalised molecules found")

    logger.info("\n Get JSON dataset files ")
    json_files = get_json_files(entities_files, normalized_molecules)
    logger.info(
        f"  {len(json_files)} dataset files contain at least one normalised molecule"
    )

    logger.info("\n Dataset and molecule relationships ")
    dataset_to_molecules = create_molecule_dataset_relationships(
        entities_files, chebi_file, pubchem_file, pdb_file
    )
    logger.info(f"  {len(dataset_to_molecules)} datasets mapped to their molecules")
    for dataset, molecules in list(dataset_to_molecules.items())[:3]:
        logger.info(f"    {dataset}: {molecules}")
    logger.info("    ...")

    logger.info("\n Normalised molecule IDs ")
    normalized_ids = get_normalized_molecule_ids(chebi_file, pubchem_file, pdb_file)
    logger.info(f"  {len(normalized_ids)} normalised ID records")
    for record in normalized_ids[:3]:
        logger.info(f"    {record}")
    logger.info("    ...")

    logger.info("\nRaw molecule and ormalised ID relationships ")
    mol_to_normalized_id = create_mol_normalisation_relationships(
        chebi_file, pubchem_file, pdb_file
    )
    logger.info(f"  {len(mol_to_normalized_id)} raw molecule → normalised ID mappings")
    for raw_name, norm_id in list(mol_to_normalized_id.items())[:3]:
        logger.info(f"    {raw_name!r} → {norm_id!r}")
    logger.info("    ...")

    logger.info("\n Create non normalized knowledge graph ")
    raw_graph = create_knowledge_graph(
        entities_files, chebi_file, pubchem_file, pdb_file, normalized=False
    )
    logger.info(
        f"  {raw_graph.number_of_nodes()} nodes, {raw_graph.number_of_edges()} edges"
    )
    visualize_knowledge_graph(raw_graph, non_normalized_knowledge_graph)
    logger.info(f"  Non normalized graph saved to {non_normalized_knowledge_graph!r}")

    logger.info("\n Create normalized knowledge graph ")
    normalized_graph = create_knowledge_graph(
        entities_files, chebi_file, pubchem_file, pdb_file, normalized=True
    )
    logger.info(
        f"  {normalized_graph.number_of_nodes()} nodes, "
        f"{normalized_graph.number_of_edges()} edges"
    )
    visualize_knowledge_graph(normalized_graph, normalized_knowledge_graph)
    logger.info(f"  Normalized graph saved to {normalized_knowledge_graph!r}")

    logger.success("\n Molecule knowledge graphs created succesfully ! ")


if __name__ == "__main__":
    main()
