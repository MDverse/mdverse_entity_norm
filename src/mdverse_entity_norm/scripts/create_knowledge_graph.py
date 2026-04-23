"""Script to create knowledge graphs."""

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd


def get_extracted_entities(
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


def create_entities_relationship(entity_file: pd.DataFrame) -> dict:
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
    entity_relationship = {}
    relationships = []
    data_set_entities = []

    for data_set in entity_file["json_file"]:
        data_set = data_set.replace("zenodo_", "zenodo\n")
        data_set = data_set.replace("figshare_", "figshare\n")
        data_set = data_set.strip(".json")
        data_set_entities.append(data_set)

    entity_relationship["entities"] = data_set_entities

    for entity_name, entity_type, json_file in zip(
        entity_file["entity"],
        entity_file["category"],
        entity_relationship["entities"],
        strict=True,
    ):
        relationships.append(
            {"source": json_file, "target": entity_name, "type": entity_type}
        )

    entity_relationship["relationships"] = relationships
    return entity_relationship


def format_all_entities(entity_relationship: dict) -> list:
    """Format entity names and collect all molecule labels.

    Parameters
    ----------
    entity_relationship : dict
        Dictionary with 'relationships' list

    Returns
    -------
    list
        List of molecule labels
    """
    all_entities = []
    for elem in entity_relationship["relationships"]:
        if len(elem["target"]) > 6:
            elem["target"] = elem["target"][:6] + "..."
        all_entities.append(elem["target"])
    return all_entities


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


def create_grounded_entities(
    grounded_molecule_path: Path, entity_relationship: dict
) -> tuple[dict, list]:
    """Match grounded molecule IDs to extracted entities.

    Parameters
    ----------
    grounded_molecule_path : Path
        Path to the grounded molecules TSV file
    entity_relationship : dict
        Dictionary with relationships list

    Returns
    -------
    tuple[dict, list]
        grounded_molecule dict with entities and relationships and a list of target IDs
    """
    grounded_molecule = {}
    relationship_grounded = []
    target = []
    entities = []

    grounded_molecule_results_known = get_grounded_molecules(grounded_molecule_path)

    for relationship in entity_relationship["relationships"]:
        entities.append(relationship["target"])

    grounded_molecule["entities"] = entities

    for molecules, molecules_ids in zip(
        grounded_molecule_results_known["MOL"],
        grounded_molecule_results_known["MOL_ID"],
        strict=True,
    ):
        if molecules in grounded_molecule["entities"]:
            relationship_grounded.append({"source": molecules, "target": molecules_ids})
            target.append(molecules_ids)

    grounded_molecule["relationships"] = relationship_grounded
    return grounded_molecule, target


def create_knowledge_graph(
    entity_relationship: dict,
    all_entities: list,
    grounded_molecule: dict,
    target: list,
    grounding: bool,
) -> nx.Graph:
    """Build a NetworkX graph from entities and optional grounding.

    Parameters
    ----------
    entity_relationship : dict
        Dataset entities and dataset->molecule relationships
    all_entities : list
        Molecule node labels
    grounded_molecule : dict
        Grounded molecule relationships
    target : list
        Grounded molecule ids nodes
    grounding : bool
        Indicate if the garph is normalized

    Returns
    -------
    nx.Graph
        The assembled knowledge graph
    """
    knowledge_graph = nx.Graph()
    knowledge_graph.add_nodes_from(entity_relationship["entities"], color="#f8ed62")
    knowledge_graph.add_nodes_from(all_entities, color="skyblue")

    for relationship in entity_relationship["relationships"]:
        knowledge_graph.add_edge(relationship["source"], relationship["target"])

    if grounding:
        knowledge_graph.add_nodes_from(target, color="#ffbaba")
        for relationship in grounded_molecule["relationships"]:
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


if __name__ == "__main__":
    entities_path = Path("data/entities.tsv")
    grounded_molecules_path = Path("results/ground_molecule/grounded_molecules.tsv")

    entity_file = get_extracted_entities(entities_path, number_of_datasets=10)
    entity_relationship = create_entities_relationship(entity_file)
    all_entities = format_all_entities(entity_relationship)
    grounded_molecule, target = create_grounded_entities(
        grounded_molecules_path, entity_relationship
    )

    knowledge_graph = create_knowledge_graph(
        entity_relationship, all_entities, grounded_molecule, target, grounding=False
    )
    grounded_knowledge_graph = create_knowledge_graph(
        entity_relationship, all_entities, grounded_molecule, target, grounding=True
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
