"""Script to create knowledge graphs."""

import json
import sys
from pathlib import Path

import click
import networkx as nx
import pandas as pd
from loguru import logger
from pyvis.network import Network

IONS = {
    "na",
    "na+",
    "cl",
    "cl-",
    "nacl",
}


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
    working_files = entity_file["json_file"].unique()[:]
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
        entity_name_clean = entity_name.lower().strip()
        if entity_name_clean in IONS:
            continue
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
    for _, row in filtered.iterrows():
        relationships.append(
            {"source": row["MOL"], "target": row["MOL_TYPE"] + "\n" + row["MOL_ID"]}
        )
    return relationships


def create_knowledge_graph(
    extracted_molecules_entities: list,
    extracted_molecules_relationships: list,
    grounded_molecules_relationships: list,
    grounded_molecules_entities: list,
    grounding: bool,
) -> nx.Graph:
    # Datasets with a least one edge
    connected_datasets = set()
    connected_datasets.update(
        relationship["source"] for relationship in extracted_molecules_relationships
    )

    knowledge_graph = nx.Graph()
    # We only add non empty dataset
    for ds in extracted_molecules_entities:
        if ds in connected_datasets:
            knowledge_graph.add_node(ds, color="#f8ed62")

    knowledge_graph.add_nodes_from(grounded_molecules_entities, color="skyblue")

    for relationship in extracted_molecules_relationships:
        knowledge_graph.add_edge(relationship["source"], relationship["target"])

    if grounding:
        grounding_ids = []
        for rel in grounded_molecules_relationships:
            grounding_ids.append(rel["target"])
        knowledge_graph.add_nodes_from(grounding_ids, color="#ffbaba")
        for relationship in grounded_molecules_relationships:
            knowledge_graph.add_edge(relationship["source"], relationship["target"])

    return knowledge_graph


def create_force_field_knowledge_graph(
    entities_path: Path,
    ffm_ground_path: Path,
    grounded: bool,
) -> nx.Graph:
    # We retreive the force fields entities
    entity_file = pd.read_csv(entities_path, sep="\t")
    entity_file = entity_file[entity_file["category"] == "FFM"]
    entity_file = entity_file.drop_duplicates(subset=["json_file", "entity"])

    # We get the force field dictionary
    with open(ffm_ground_path) as f:
        ffm_data = json.load(f)
    force_fields = ffm_data["force_fields"]

    # We build a dictionary with the proper name and its aliases
    synonym_to_name = {}
    for ff in force_fields:
        canonical_name = ff["name"]
        for synonym in ff["aliases"]:
            synonym_to_name[synonym.lower().strip()] = canonical_name

    # We create the force field knowledge graph
    graph = nx.Graph()

    for _, row in entity_file.iterrows():
        entity = row["entity"]
        json_file = row["json_file"]

        dataset = json_file.replace("zenodo_", "zenodo\n")
        dataset = dataset.replace("figshare_", "figshare\n")
        dataset = dataset.strip(".json")

        entity_clean = entity.lower().strip()
        if entity_clean in synonym_to_name:
            canonical_name = synonym_to_name[entity_clean]
            # We ad the nodes (entity: ff | dataset | canoniczl: ff grounded)
            if dataset not in graph.nodes:
                graph.add_node(dataset, color="#FFD700", size=30, borderWidth=3)
            if entity not in graph.nodes:
                graph.add_node(entity, color="#4DA6FF", size=25, borderWidth=3)
            if grounded:
                if canonical_name not in graph.nodes:
                    graph.add_node(
                        canonical_name, color="#FF8080", size=25, borderWidth=3
                    )

            # We add the link betwee the edges between the ff and its dataset
            # and between the ff and its grounded name
            graph.add_edge(dataset, entity)
            if grounded:
                graph.add_edge(entity, canonical_name)

    return graph


# def create_knowledge_graph(
#     extracted_molecules_entities: list,
#     extracted_molecules_relationships: list,
#     grounded_molecules_relationships: list,
#     grounded_molecules_entities: list,
#     grounding: bool,
# ) -> nx.Graph:
#     """Build the NetworkX knowledge graph.

#     Parameters
#     ----------
#     extracted_molecules_entities : list
#         Dataset node labels
#     extracted_molecules_relationships : list
#         Edges between datasets and molecules
#     grounded_molecules_relationships : list
#         Edges between molecules and grounding IDs
#     grounded_molecules_entities : list
#         Molecule node labels
#     grounding : bool
#         Whether to include grounding ID nodes and edges

#     Returns
#     -------
#     nx.Graph
#         The assembled knowledge graph
#     """
#     grounding_ids = []
#     for rel in grounded_molecules_relationships:
#         grounding_ids.append(rel["target"])

#     knowledge_graph = nx.Graph()
#     knowledge_graph.add_nodes_from(extracted_molecules_entities, color="#f8ed62")
#     knowledge_graph.add_nodes_from(grounded_molecules_entities, color="skyblue")

#     for relationship in extracted_molecules_relationships:
#         knowledge_graph.add_edge(relationship["source"], relationship["target"])

#     if grounding:
#         knowledge_graph.add_nodes_from(grounding_ids, color="#ffbaba")
#         for relationship in grounded_molecules_relationships:
#             knowledge_graph.add_edge(relationship["source"], relationship["target"])

#     return knowledge_graph


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


def visualize_graph(graph, output_path):

    net = Network(height="900px", width="100%")
    net.barnes_hut(
        gravity=-3000,
        central_gravity=0.2,
        spring_length=180,
        spring_strength=0.03,
        damping=0.09,
    )
    net.from_nx(graph)
    for edge in net.edges:
        edge["width"] = 3
    for node in net.nodes:
        node["font"] = {"size": 30, "face": "Arial", "color": "black", "bold": True}
    net.bgcolor = "#f8f8f8"

    net.write_html(output_path)

    print(f"Graph saved to: {output_path}")


def print_graph_stats(knowledge_graph: nx.Graph) -> None:
    """Print basic statistics about the graph."""
    num_components = nx.number_connected_components(knowledge_graph)
    logger.info(f"Number of nodes: {knowledge_graph.number_of_nodes()}")
    logger.info(f"Density: {nx.density(knowledge_graph)}")
    logger.info(f"Number of edges: {knowledge_graph.number_of_edges()}")
    logger.info(f"Number of disjoint subgraphs: {num_components}")
    logger.info("CONNECTED COMPONENT:")
    for i, component in enumerate(list(nx.connected_components(knowledge_graph))):
        logger.info(f"Connected components {i + 1}:{component}")


# def find_grounding_bridges(
#     knowledge_graph: nx.Graph,
#     grounded_knowledge_graph: nx.Graph,
#     dataset_nodes: set,
# ) -> list:

#     # dictionnaire qui va stocker pour chaque grounding_id
#     # la liste des (dataset, molecule) qui y sont reliés
#     grounding_to_datasets = {}

#     # on parcourt tous les noeuds du graphe avec grounding
#     for node in grounded_knowledge_graph.nodes:
#         # les noeuds de grounding sont ceux qui n'existent pas dans le graphe sans grounding
#         if node not in knowledge_graph.nodes:
#             # on parcourt les molécules reliées à ce grounding_id
#             for mol in grounded_knowledge_graph[node]:
#                 # on parcourt les datasets reliés à cette molécule
#                 for ds in knowledge_graph[mol]:
#                     # on vérifie que c'est bien un dataset et pas une molécule
#                     if ds in dataset_nodes:
#                         # si le grounding_id n'est pas encore dans le dictionnaire, on crée une liste vide
#                         if node not in grounding_to_datasets:
#                             grounding_to_datasets[node] = []
#                         # on ajoute le couple (dataset, molecule) à la liste
#                         grounding_to_datasets[node].append((ds, mol))

#     # liste finale des résultats
#     results = []

#     # on parcourt chaque grounding_id et sa liste de (dataset, molecule)
#     for grounding_id in grounding_to_datasets:
#         ds_mol_list = grounding_to_datasets[grounding_id]
#         # on génère toutes les paires possibles de (dataset, molecule)
#         for i in range(len(ds_mol_list)):
#             for j in range(i + 1, len(ds_mol_list)):
#                 # on récupère les deux couples (dataset, molecule)
#                 ds1, mol1 = ds_mol_list[i]
#                 ds2, mol2 = ds_mol_list[j]
#                 # on ignore si c'est le même dataset
#                 if ds1 == ds2:
#                     continue

#                 # on récupère toutes les molécules du dataset 1
#                 mols_ds1 = set(knowledge_graph[ds1])
#                 # on récupère toutes les molécules du dataset 2
#                 mols_ds2 = set(knowledge_graph[ds2])
#                 # si les deux datasets ont au moins une molécule avec le même nom exact, on ignore
#                 if len(mols_ds1 & mols_ds2) > 0:
#                     continue

#                 # sinon on ajoute le résultat : les deux datasets, leurs molécules et le grounding qui les relie
#                 results.append(
#                     {
#                         "pair": (ds1, ds2),
#                         "mol_ds1": mol1,
#                         "mol_ds2": mol2,
#                         "grounding_id": grounding_id,
#                     }
#                 )

#     return results


# def find_force_field_bridges(
#     entity_file: pd.DataFrame,
#     ffm_ground_path: Path,
# ):
#     import json

#     with open(ffm_ground_path, encoding="utf-8") as f:
#         ffm_data = json.load(f)

#     force_fields = ffm_data["force_fields"]

#     synonym_map = {}

#     for ff in force_fields:
#         canonical = ff["name"]

#         for syn in ff.get("aliases", []):
#             key = syn.lower().strip()
#             synonym_map[key] = {"canonical": canonical, "synonym": syn}

#     matched = []
#     unmatched = []

#     for _, row in entity_file.iterrows():
#         entity = str(row["entity"]).lower().strip()
#         json_file = row["json_file"]

#         dataset = json_file.replace("zenodo_", "zenodo\n")
#         dataset = dataset.replace("figshare_", "figshare\n")
#         dataset = dataset.strip(".json")

#         if entity in synonym_map:
#             info = synonym_map[entity]

#             matched.append(
#                 {
#                     "dataset": dataset,
#                     "raw_entity": row["entity"],
#                     "synonym_used": info["synonym"],
#                     "canonical_force_field": info["canonical"],
#                 }
#             )
#         else:
#             unmatched.append({"dataset": dataset, "entity": row["entity"]})

#     return matched, unmatched


# def create_force_field_diff_graph(matched):
#     import networkx as nx

#     G = nx.Graph()

#     for m in matched:
#         dataset = m["dataset"]
#         synonym = m["synonym_used"]
#         canonical = m["canonical_force_field"]

#         if dataset not in G:
#             G.add_node(dataset, color="#f8ed62")
#         if synonym not in G:
#             G.add_node(synonym, color="skyblue")

#         if canonical not in G:
#             G.add_node(canonical, color="#ffbaba")

#         G.add_edge(dataset, synonym)
#         G.add_edge(synonym, canonical)

#     return G


@click.command()
@click.option(
    "--extracted_entities_path",
    default="data/entities.tsv",
    type=click.Path(file_okay=True, path_type=Path),
    help="Path to the TSV file containing the extracted entities",
)
# @click.option(
#     "--grounded_molecules_path",
#     default="results/ground_molecule/grounded_molecules.tsv",
#     type=click.Path(file_okay=True, path_type=Path),
#     help="Path to the TSV file containing the grounded molecules",
# )
@click.option(
    "--number_of_datasets",
    default=10,
    type=int,
    help="Number of datasets in the graph",
)
def main_create_knowledge_graphs(
    extracted_entities_path,
    # grounded_molecules_path,
    number_of_datasets,
):
    #     """Create and save the knowledge graphs, and display graph statistics.

    #     Parameters
    #     ----------
    #     extracted_entities_path : Path
    #         Path to the extracted entities file
    #     grounded_molecules_path : Path
    #         Path to the grounded molecules file
    #     number_of_datasets : int
    #         Number of datasets in the graph
    #     """
    #     extracted_entity_file = get_extracted_molecules(
    #         extracted_entities_path, number_of_datasets
    #     )
    #     grounded_entity_file = get_grounded_molecules(grounded_molecules_path)
    #     extracted_entity_file_entities = create_extracted_molecules_entities(
    #         extracted_entity_file
    #     )
    #     extracted_entity_file_relationship = create_extracted_molecules_relationships(
    #         extracted_entity_file, grounded_entity_file
    #     )
    #     grounded_molecule_entities = create_grounded_molecules_entities(
    #         grounded_entity_file, extracted_entity_file_relationship
    #     )
    #     grounded_entity_file_relationships = create_grounded_molecule_relationship(
    #         grounded_entity_file, grounded_molecule_entities
    #     )

    #     knowledge_graph = create_knowledge_graph(
    #         extracted_entity_file_entities,
    #         extracted_entity_file_relationship,
    #         grounded_entity_file_relationships,
    #         grounded_molecule_entities,
    #         grounding=False,
    #     )
    #     grounded_knowledge_graph = create_knowledge_graph(
    #         extracted_entity_file_entities,
    #         extracted_entity_file_relationship,
    #         grounded_entity_file_relationships,
    #         grounded_molecule_entities,
    #         grounding=True,
    #     )
    #     new_edges = (grounded_knowledge_graph.edges()) - (knowledge_graph.edges())

    # logger.info("KNOWLEDGE GRAPH")
    # print_graph_stats(knowledge_graph)
    # logger.info("GROUNDED KNOWLEDGE GRAPH")
    # print_graph_stats(grounded_knowledge_graph)

    # visualize_graph(
    #     knowledge_graph,
    #     grounded_molecule_entities,
    #     output_path=Path("results/ground_molecule/knowledge_graph.png"),
    #     highlight_edges=None,
    # )
    # visualize_graph(
    #     grounded_knowledge_graph,
    #     grounded_molecule_entities,
    #     output_path=Path("results/ground_molecule/knowledge_graph_grounded.png"),
    #     highlight_edges=new_edges,
    # )

    # visualize_graph(
    #     knowledge_graph,
    #     "results/ground_molecule/knowledge_graph.html",
    #     # highlight_new_edges=new_edges,
    # )
    # visualize_graph(
    #     grounded_knowledge_graph,
    #     "results/ground_molecule/knowledge_graph_grounded.html",
    #     # highlight_new_edges=new_edges,
    # )
    # dataset_nodes = set(extracted_entity_file_entities)
    # grounding_bridges = find_grounding_bridges(
    #     knowledge_graph,
    #     grounded_knowledge_graph,
    #     dataset_nodes,
    # )

    ff_graph = create_force_field_knowledge_graph(
        Path("data/entities.tsv"), Path("data/FFM_ground.json"), False
    )
    ff_graph_grounded = create_force_field_knowledge_graph(
        Path("data/entities.tsv"), Path("data/FFM_ground.json"), True
    )

    logger.info("FORCE FIELD KNOWLEDGE GRAPH")
    print_graph_stats(ff_graph)

    visualize_graph(ff_graph, "results/force_field/knowledge_graph_ff.html")
    visualize_graph(
        ff_graph_grounded, "results/force_field/knowledge_graph_ff_grounded.html"
    )
    # matched, unmatched = find_force_field_bridges(
    #     extracted_entity_file,
    #     Path("data/FFM_ground.json"),
    # )

    # logger.info(f"Matched force fields: {len(matched)}")
    # logger.info(f"Unmatched force fields: {len(unmatched)}")


if __name__ == "__main__":
    logger.remove()
    logger_format = (
        "{time:YYYY-MM-DD HH:mm:ss} "
        "| <level>{level:<8}</level> "
        "| <level>{message}</level>"
    )
    logger.add(sys.stdout, format=logger_format, level="DEBUG")
    main_create_knowledge_graphs()
