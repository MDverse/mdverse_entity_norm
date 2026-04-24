"""Script to extract entities from onthology."""

import pathlib
import sys


def read_file(filepath):
    """Open a file and return its content as one big string.

    Parameters
    ----------
    filepath (Path): Path to the ontology file

    Returns
    -------
        str: the whole file in a string
    """
    content = pathlib.Path(filepath).read_text()
    return content


def split_into_class_blocks(file_content):
    """Split the whole text in classes.

    Parameters
    ----------
    file_content(str) : the string containing the whole file

    Returns
    -------
        list: contains each class found in the file
    """
    class_blocks = []

    parts = file_content.split("<owl:Class rdf:about=")
    for part in parts[1:]:
        block = "<owl:Class rdf:about=" + part

        end_tag = "</owl:Class>"
        end_position = block.find(end_tag)

        if end_position != -1:
            block = block[: end_position + len(end_tag)]
            class_blocks.append(block)

    return class_blocks


def get_label(block):
    """Return the label of  the class.

    Parameters
    ----------
    bloc(str): The class string

    Returns
    -------
     str: the entity label
    """
    start_marker = "<rdfs:label"
    end_marker = "</rdfs:label>"

    position = block.find(start_marker)
    if position == -1:
        return None

    tag_end = block.find(">", position)
    if tag_end == -1:
        return None

    text_start = tag_end + 1
    text_end = block.find(end_marker, text_start)
    if text_end == -1:
        return None

    label = block[text_start:text_end].strip()
    return label


def get_link(block):
    """Return the link of the entity.

    Parameters
    ----------
    bloc(str): The class string

    Returns
    -------
     str: the entity link
    """
    marker = 'rdf:about="'
    position = block.find(marker)
    if position == -1:
        return "not found"

    start = position + len(marker)
    end = block.find('"', start)
    if end == -1:
        return "not found"

    return block[start:end]


def get_parent_link(block):
    """Return the parent link of the entity.

    Parameters
    ----------
    bloc(str): The class string

    Returns
    -------
     str: the position of the parent calss
    """
    marker = '<rdfs:subClassOf rdf:resource="'
    position = block.find(marker)
    if position == -1:
        return None

    start = position + len(marker)
    end = block.find('"', start)
    if end == -1:
        return None

    return block[start:end]


def build_lookup_tables(class_blocks):
    """Retuenr a tuple with label an linkto look for.

    Parameters
    ----------
    class_blocks(List): list of all  the extracted classes

    Returns
    -------
     Tuple: label and link to look for while building the path
    """
    label_to_block = {}
    link_to_label = {}

    for block in class_blocks:
        label = get_label(block)
        link = get_link(block)

        if link and link != "not found":
            link_to_label[link] = label or ""

        if label:
            # Store with lowercase key so searches are case-insensitive.
            label_to_block[label.lower()] = block

    return label_to_block, link_to_label


def build_path(block, label_to_block, link_to_label):
    """Build the Path to the entity.

    Parameters
    ----------
    block(str): The mothe class
    label_to_block(str): The name of the class
    link_to_label(str): link to the label

    Returns
    -------
    str
        the path to the entity
    """
    path_parts = []

    current_block = block

    max_steps = 100
    steps = 0

    while current_block is not None and steps < max_steps:
        steps += 1
        label = get_label(current_block)
        if label:
            path_parts.append(label)
        else:
            path_parts.append(get_link(current_block))

        parent_url = get_parent_link(current_block)
        if parent_url is None:
            break
        parent_label = link_to_label.get(parent_url)
        if parent_label is None:
            path_parts.append(parent_url)
            break

        current_block = label_to_block.get(parent_label)

    path_parts.reverse()
    return " > ".join(path_parts)


def search_name(name, label_to_block, link_to_label):
    """Search the entity name through the ontology.

    Parameters
    ----------
    name (str): the entity name
    label_to_block (str): The name in the class
    link_to_label (str):  the link to the entity

    Returns
    -------
        list: the results to put in the tsv file ( name, status, link, path)
    """
    block = label_to_block.get(name.lower())

    if block is None:
        return [name, "not found", "not found", "not found"]

    link = get_link(block)
    path = build_path(block, label_to_block, link_to_label)
    status = "found"

    return [name, status, path, link]


def read_names(filepath):
    """Read the names in the name file.

    Parameters
    ----------
    filepath (Path): Path to the file with the names taht have to be found

    Returns
    -------
        list: A list with all the names from the file
    """
    names = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if name:
                names.append(name)
    return names


def write_tsv(rows, output_filepath):
    """Write the results in the tsv file.

    Parameters
    ----------
    rows (list): List of rows to write to the TSV file
    output_filepath (str): Path to the output TSV file
    """
    with open(output_filepath, "w", encoding="utf-8") as f:
        # Header
        f.write("name\tstatus\tpath\tlink\n")
        # One line per entity
        for row in rows:
            line = "\t".join(row) + "\n"
            f.write(line)


def main():
    """Execute the main script to search entities in an OWL ontology.

    Reads an OWL file, searches for entities by name, and writes results to a TSV file.
    Expects three command-line arguments: OWL file, names file, and output TSV file.
    """
    if len(sys.argv) != 4:
        print(
            "Usage: python search_owl_entities.py <owl_file> <names_file> <output_tsv>"
        )
        print(
            "Example: python search_owl_entities.py molsim-full.owl names.txt results.tsv"
        )
        sys.exit(1)

    owl_file = sys.argv[1]
    names_file = sys.argv[2]
    output_file = sys.argv[3]

    print(f"Reading OWL file: {owl_file} ...")
    file_content = read_file(owl_file)
    print("  Done.")

    print("Splitting into owl:Class blocks ...")
    class_blocks = split_into_class_blocks(file_content)
    print(f"  Found {len(class_blocks)} class blocks.")

    print("Building lookup tables ...")
    label_to_block, link_to_label = build_lookup_tables(class_blocks)
    print(f"  Indexed {len(label_to_block)} labelled classes.")

    print(f"Reading names from: {names_file} ...")
    names = read_names(names_file)
    print(f"  {len(names)} name(s) to search.")

    print("Searching ...")
    results = []
    for name in names:
        row = search_name(name, label_to_block, link_to_label)
        results.append(row)
        status_text = row[1]
        print(f"  '{name}' → {status_text}")

    print(f"Writing results to: {output_file} ...")
    write_tsv(results, output_file)
    print("  Done!")
    print(f"\nFinished. Results saved to '{output_file}'.")


if __name__ == "__main__":
    main()
