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
    entity_file = entity_file[entity_file["category"] == "MOL"]
    working_files = entity_file["json_file"].unique()[:number_of_datasets]
    entity_file = entity_file[entity_file["json_file"].isin(working_files)]
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
    logger.info(f"length after grounding :{len(grounded_molecule_results_known)} ")
    return grounded_molecule_results_known


def create_extracted_molecules_entities(entity_file: pd.DataFrame) -> list:
    """Create a dictionary with dataset entities and their relationships.

    Parameters
    ----------
    entity_file : pd.DataFrame
        Contains the extracted molecules from each dataset

    Returns
    -------
    dict
        Dictionary with entities (dataset) and relationships (dataset -> molecule)
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
    relationships = []
    for entity_name, json_file in zip(
        entity_file["entity"],
        entity_file["json_file"],
        strict=True,
    ):
        if entity_name in list(grounded_molecule_results_known["MOL"]):
            clean_json_file = json_file.replace("zenodo_", "zenodo\n")
            clean_json_file = clean_json_file.replace("figshare_", "figshare\n")
            clean_json_file = clean_json_file.strip(".json")
            relationships.append({"source": clean_json_file, "target": entity_name})
    return relationships


def create_grounded_molecules_entities(
    grounded_molecule_results_known: pd.DataFrame,
    extracted_molecule_relationships: list,
) -> list:
    grounded_molecule_entities = []
    extracted_molecules = []

    for relationship in extracted_molecule_relationships:
        extracted_molecules.append(relationship["target"])

    for molecule in grounded_molecule_results_known["MOL"]:
        if molecule in extracted_molecules:
            grounded_molecule_entities.append(molecule)
    return grounded_molecule_entities


def create_grounded_molecule_relationship(
    grounded_molecule_results_known: pd.DataFrame, grounded_molecule_entities: list
):
    relationships = []

    for entity_name, grounded_molecule_name, grounded_molecule_id in zip(
        grounded_molecule_entities,
        grounded_molecule_results_known["MOL"],
        grounded_molecule_results_known["MOL_ID"],
        strict=False,
    ):
        if entity_name == grounded_molecule_name:
            relationships.append(
                {"source": entity_name, "target": grounded_molecule_id}
            )
    return relationships


def create_knowledge_graph(
    extracted_molecules_entites: list,
    extracted_molecules_relationships: list,
    grounded_molecules_relationships: list,
    grounded_molecules_entities: list,
    grounding: bool,
) -> nx.Graph:

    extracted_molecules = {}
    extracted_molecules["entities"] = extracted_molecules_entites
    extracted_molecules["relationships"] = extracted_molecules_relationships
    grounded_molecules = {}
    grounded_molecules["entities"] = grounded_molecules_entities
    grounded_molecules["relationship"] = grounded_molecules_relationships

    grounding_id = []
    for relationship in grounded_molecules_relationships:
        grounding_id.append(relationship["target"])

    knowledge_graph = nx.Graph()
    logger.info(f"Adding dataset nodes : {extracted_molecules['entities']}")
    knowledge_graph.add_nodes_from(extracted_molecules["entities"], color="#f8ed62")
    logger.info(f"Adding molecules nodes : {grounded_molecules['entities']}")
    knowledge_graph.add_nodes_from(grounded_molecules["entities"], color="skyblue")

    logger.info(
        f"extracted molecule relationships : {extracted_molecules_relationships}"
    )
    for relationship in extracted_molecules["relationships"]:
        knowledge_graph.add_edge(relationship["source"], relationship["target"])

    if grounding:
        knowledge_graph.add_nodes_from(grounding_id, color="#ffbaba")
        for relationship in grounded_molecules_relationships:
            knowledge_graph.add_edge(relationship["source"], relationship["target"])

    return knowledge_graph


def visualize_graph(knowledge_graph: nx.Graph, output_path: Path) -> None:
    """Draw the knowledge graph and save it to a file.

    Parameters
    ----------
    knowledge_graph : nx.Graph
        The graph to visualize
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
    pos = nx.spring_layout(knowledge_graph, k=0.5, iterations=50)

    fig, ax = plt.subplots(figsize=(20, 16))
    nx.draw(
        knowledge_graph,
        pos,
        ax=ax,
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
    help="Path to the tsv output file containing the extracted entities",
)
@click.option(
    "--grounded_molecules_path",
    default="results/ground_molecule/grounded_molecules.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the tsv output file containing the grounfded entities",
)
@click.option(
    "--number_of_datasets",
    default=10,
    type=int,
    help="number of datasets in the graphe",
)
def main_create_knoledge_graphes(
    extracted_entities_path, grounded_molecules_path, number_of_datasets
):
    """Create and save the knowledge graphes, display the graphe statistics.

    Parameters
    ----------
    extracted_entities_path(Path): path to the extracted entities
    grounded_molecules_path(Path): path to the grounded molecules file
    number_of_dataset(int): number of dataset in the graph
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
    logger.info(f"grounded_molecule_entities : {grounded_molecule_entities}")
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
    print("kowledge graph")
    print_graph_stats(knowledge_graph)
    print("grounded knowledge graph")
    print_graph_stats(grounded_knowledge_graph)
    visualize_graph(
        knowledge_graph,
        output_path=Path("results/ground_molecule/knowledge_graph.png"),
    )
    visualize_graph(
        grounded_knowledge_graph,
        output_path=Path("results/ground_molecule/knowledge_graph_grounded.png"),
    )


if __name__ == "__main__":
    main_create_knoledge_graphes()
