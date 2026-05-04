"""Script to create knowledge graphs."""

from pathlib import Path

import click
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from loguru import logger


def get_extracted_molecules(
    entities_path: Path, number_of_datasets: int
) -> pd.DataFrame:
    """Load the entities file and extract molecule entities.

    Parameters
    ----------
    entities_path : Path
        Path to the entities TSV file
    number_of_datasets : int
        Number of datasets used to create the graph

    Returns
    -------
    pd.DataFrame
        Filtered dataframe containing molecule entities
    """
    entity_file = pd.read_csv(entities_path, sep="\t")
    # entity_file = entity_file[entity_file["category"] == "MOL"]
    # working_files = entity_file["json_file"].unique()[:number_of_datasets]
    # entity_file = entity_file[entity_file["json_file"].isin(working_files)]
    json_files = [
        "zenodo_1293813.json",
        "zenodo_1488094.json",
        "zenodo_247386.json",
        "zenodo_5060102.json",
        "zenodo_7007107.json",
        "zenodo_34415.json",
        "zenodo_1219494.json",
    ]
    entity_file = entity_file[entity_file["json_file"].isin(json_files)]
    entity_file = entity_file.drop_duplicates(subset=["json_file", "entity"])
    return entity_file


def get_grounded_molecules(grounded_molecule_path: Path) -> pd.DataFrame:
    """Load the grounded molecule file and keep only known entries.

    Parameters
    ----------
    grounded_molecule_path : Path
        Path to the grounded molecules TSV file

    Returns
    -------
    pd.DataFrame
        Rows where MOL_TYPE is not Unknown
    """
    grounded_entity_file = pd.read_csv(grounded_molecule_path, sep="\t")
    grounded_molecule_results_known = grounded_entity_file[
        grounded_entity_file["MOL_TYPE"] != "Unknown"
    ]
    return grounded_molecule_results_known


def create_extracted_molecules_entities(entity_file: pd.DataFrame) -> list:
    """Create a list of dataset node labels.

    Parameters
    ----------
    entity_file : pd.DataFrame
        Contains the extracted molecules from each dataset

    Returns
    -------
    list
        List of cleaned dataset labels
    """
    data_set_entities = []

    for data_set in entity_file["json_file"]:
        data_set = data_set.replace("zenodo_", "zenodo\n")
        data_set = data_set.replace("figshare_", "figshare\n")
        data_set = data_set.strip(".json")
        data_set_entities.append(data_set)

    return data_set_entities


def create_extracted_molecules_relationships(
    entity_file: pd.DataFrame, grounded_molecule_results_known: pd.DataFrame
) -> list:
    """Create edges between dataset nodes and molecule nodes.

    Parameters
    ----------
    entity_file : pd.DataFrame
        Contains the extracted molecules from each dataset
    grounded_molecule_results_known : pd.DataFrame
        Contains the grounded molecules

    Returns
    -------
    list
        List of dicts with 'source' (dataset) and 'target' (molecule)
    """
    relationships = []
    known_molecules = set(grounded_molecule_results_known["MOL"])

    for entity_name, json_file in zip(
        entity_file["entity"],
        entity_file["json_file"],
        strict=True,
    ):
        if entity_name in known_molecules:
            clean_json_file = json_file.replace("zenodo_", "zenodo\n")
            clean_json_file = clean_json_file.replace("figshare_", "figshare\n")
            clean_json_file = clean_json_file.strip(".json")
            relationships.append({"source": clean_json_file, "target": entity_name})
    return relationships


def create_grounded_molecules_entities(
    grounded_molecule_results_known: pd.DataFrame,
    extracted_molecule_relationships: list,
) -> list:
    """Return the subset of grounded molecules that appear in the extracted relationships.

    Parameters
    ----------
    grounded_molecule_results_known : pd.DataFrame
        Contains the grounded molecules
    extracted_molecule_relationships : list
        Edges between datasets and molecules

    Returns
    -------
    list
        Molecule names present in both sources
    """
    extracted_molecules = []
    for i in range(len(extracted_molecule_relationships)):
        extracted_molecules.append(extracted_molecule_relationships[i]["target"])

    grounded_molecule_entities = []
    mol_list = list(grounded_molecule_results_known["MOL"])
    for i in range(len(mol_list)):
        if mol_list[i] in extracted_molecules:
            grounded_molecule_entities.append(mol_list[i])

    return grounded_molecule_entities


def create_grounded_molecule_relationship(
    grounded_molecule_results_known: pd.DataFrame, grounded_molecule_entities: list
) -> list:
    """Create edges between molecule nodes and their grounding IDs.

    Parameters
    ----------
    grounded_molecule_results_known : pd.DataFrame
        Contains the grounded molecules with their IDs
    grounded_molecule_entities : list
        Molecule names to include in the graph

    Returns
    -------
    list
        List of dicts with 'source' (molecule name) and 'target' (grounding ID)
    """
    filtered = grounded_molecule_results_known[
        grounded_molecule_results_known["MOL"].isin(grounded_molecule_entities)
    ].drop_duplicates(subset=["MOL"])

    relationships = []
    for num, row in filtered.iterrows():
        logger.info(row)
        relationships.append(
            {"source": row["MOL"], "target": row["MOL_TYPE"] + "\n" + row["MOL_ID"]}
        )

    logger.info(f"RELATIONSHIPS = {relationships}")
    return relationships


def create_knowledge_graph(
    extracted_molecules_entities: list,
    extracted_molecules_relationships: list,
    grounded_molecules_relationships: list,
    grounded_molecules_entities: list,
    grounding: bool,
) -> nx.Graph:
    """Build the NetworkX knowledge graph.

    Parameters
    ----------
    extracted_molecules_entities : list
        Dataset node labels
    extracted_molecules_relationships : list
        Edges between datasets and molecules
    grounded_molecules_relationships : list
        Edges between molecules and grounding IDs
    grounded_molecules_entities : list
        Molecule node labels
    grounding : bool
        Whether to include grounding ID nodes and edges

    Returns
    -------
    nx.Graph
        The assembled knowledge graph
    """
    grounding_ids = []
    for rel in grounded_molecules_relationships:
        grounding_ids.append(rel["target"])

    knowledge_graph = nx.Graph()
    knowledge_graph.add_nodes_from(extracted_molecules_entities, color="#f8ed62")
    knowledge_graph.add_nodes_from(grounded_molecules_entities, color="skyblue")

    for relationship in extracted_molecules_relationships:
        knowledge_graph.add_edge(relationship["source"], relationship["target"])

    if grounding:
        knowledge_graph.add_nodes_from(grounding_ids, color="#ffbaba")
        for relationship in grounded_molecules_relationships:
            knowledge_graph.add_edge(relationship["source"], relationship["target"])

    return knowledge_graph


def get_molecule_label(molecule_entities: list) -> dict:
    """Build a truncated display-label dict for molecule nodes.

    Parameters
    ----------
    molecule_entities : list
        List of molecule names

    Returns
    -------
    dict
        Mapping from molecule name to a (possibly truncated) display label
    """
    label_dict = {}
    for molecule_name in molecule_entities:
        if len(molecule_name) > 6:
            label_dict[molecule_name] = molecule_name[:6] + "..."
        else:
            label_dict[molecule_name] = molecule_name
    return label_dict


def visualize_graph(
    knowledge_graph: nx.Graph,
    grounded_molecules_entities: list,
    output_path: Path,
) -> None:
    """Draw the knowledge graph and save it to a file.

    Parameters
    ----------
    knowledge_graph : nx.Graph
        The graph to visualize
    grounded_molecules_entities : list
        Molecule node names used to build truncated labels
    output_path : Path
        Path where the image will be saved
    """
    if knowledge_graph is None or len(knowledge_graph.nodes) == 0:
        print("Graph is empty or None. Cannot visualize.")
        return

    node_colors = [
        knowledge_graph.nodes[node].get("color", "skyblue")
        for node in knowledge_graph.nodes
    ]

    molecule_label_dict = get_molecule_label(grounded_molecules_entities)
    labels = {}
    node_list = list(knowledge_graph.nodes)
    for i in range(len(node_list)):
        if node_list[i] in molecule_label_dict:
            labels[node_list[i]] = molecule_label_dict[node_list[i]]
        else:
            labels[node_list[i]] = node_list[i]

    pos = nx.spring_layout(knowledge_graph, k=0.5, iterations=50)

    fig, ax = plt.subplots(figsize=(20, 16))
    nx.draw(
        knowledge_graph,
        pos,
        ax=ax,
        labels=labels,
        with_labels=True,
        node_color=node_colors,
        node_size=1500,
        font_size=9,
        font_weight="bold",
        edge_color="gray",
        linewidths=2.5,
        alpha=1,
    )
    ax.set_title("Knowledge Graph", fontsize=14, fontweight="bold")

    fig.savefig(output_path)
    plt.close(fig)
    print(f"Graph saved to: {output_path}")


def print_graph_stats(knowledge_graph: nx.Graph) -> None:
    """Print basic statistics about the graph."""
    num_components = nx.number_connected_components(knowledge_graph)
    print("Number of nodes:", knowledge_graph.number_of_nodes())
    print("Density:", nx.density(knowledge_graph))
    print("Isolated nodes:", nx.number_of_isolates(knowledge_graph))
    print(f"Number of disjoint subgraphs: {num_components}")


@click.command()
@click.option(
    "--extracted_entities_path",
    default="data/entities.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the TSV file containing the extracted entities",
)
@click.option(
    "--grounded_molecules_path",
    default="results/ground_molecule/grounded_molecules.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the TSV file containing the grounded molecules",
)
@click.option(
    "--number_of_datasets",
    default=10,
    type=int,
    help="Number of datasets in the graph",
)
def main_create_knowledge_graphs(
    extracted_entities_path, grounded_molecules_path, number_of_datasets
):
    """Create and save the knowledge graphs, and display graph statistics.

    Parameters
    ----------
    extracted_entities_path : Path
        Path to the extracted entities file
    grounded_molecules_path : Path
        Path to the grounded molecules file
    number_of_datasets : int
        Number of datasets in the graph
    """
    extracted_entity_file = get_extracted_molecules(
        extracted_entities_path, number_of_datasets
    )
    grounded_entity_file = get_grounded_molecules(grounded_molecules_path)
    extracted_entity_file_entities = create_extracted_molecules_entities(
        extracted_entity_file
    )
    extracted_entity_file_relationship = create_extracted_molecules_relationships(
        extracted_entity_file, grounded_entity_file
    )
    grounded_molecule_entities = create_grounded_molecules_entities(
        grounded_entity_file, extracted_entity_file_relationship
    )
    grounded_entity_file_relationships = create_grounded_molecule_relationship(
        grounded_entity_file, grounded_molecule_entities
    )

    knowledge_graph = create_knowledge_graph(
        extracted_entity_file_entities,
        extracted_entity_file_relationship,
        grounded_entity_file_relationships,
        grounded_molecule_entities,
        grounding=False,
    )
    grounded_knowledge_graph = create_knowledge_graph(
        extracted_entity_file_entities,
        extracted_entity_file_relationship,
        grounded_entity_file_relationships,
        grounded_molecule_entities,
        grounding=True,
    )

    print("Knowledge graph")
    print_graph_stats(knowledge_graph)
    print("Grounded knowledge graph")
    print_graph_stats(grounded_knowledge_graph)

    visualize_graph(
        knowledge_graph,
        grounded_molecule_entities,
        output_path=Path("results/ground_molecule/knowledge_graph.png"),
    )
    visualize_graph(
        grounded_knowledge_graph,
        grounded_molecule_entities,
        output_path=Path("results/ground_molecule/knowledge_graph_grounded.png"),
    )


if __name__ == "__main__":
    main_create_knowledge_graphs()
