import pandas as pd


def load_dataset(file_path):
    """
    Load a TSV file into a pandas DataFrame.

    Parameters
    ----------
        file_path (str): Path to the input TSV file.

    Returns
    -------
        pd.DataFrame: Loaded dataset with columns [model, input, result].
    """
    dataframe = pd.read_csv(
        file_path, sep="\t", header=None, names=["model", "input", "result"]
    )
    return dataframe


def compute_occurrences(dataframe):
    """
    Count occurrences of each (model, input, result) combination.

    Parameters
    ----------
        dataframe (pd.DataFrame): Input dataset.

    Returns
    -------
        pd.DataFrame: DataFrame with columns [model, input, result, count].
    """
    occurrence_counts = dataframe.value_counts().reset_index()
    occurrence_counts.columns = ["model", "input", "result", "count"]
    return occurrence_counts


def add_model_totals(occurrence_dataframe):
    """
    Add a column with the total count per model.

    Parameters
    ----------
        occurrence_dataframe (pd.DataFrame): Data with counts per row.

    Returns
    -------
        pd.DataFrame: DataFrame with an additional 'total' column.
    """
    occurrence_dataframe["total"] = occurrence_dataframe.groupby("model")[
        "count"
    ].transform("sum")
    return occurrence_dataframe


def sort_results(occurrence_dataframe):
    """
    Sort results by total count and individual count.

    Parameters
    ----------
        occurrence_dataframe (pd.DataFrame): Data with counts and totals.

    Returns
    -------
        pd.DataFrame: Sorted DataFrame.
    """
    sorted_dataframe = occurrence_dataframe.sort_values(
        by=["total", "count"], ascending=False
    )
    return sorted_dataframe


def save_to_tsv(dataframe, output_path):
    """
    Save a DataFrame to a TSV file.

    Parameters
    ----------
        dataframe (pd.DataFrame): Data to save.
        output_path (str): Output file path.
    """
    dataframe.to_csv(output_path, sep="\t", index=False)


def main():
    input_file_path = "../llmerr.tsv"
    output_file_path = "output.tsv"

    dataset = load_dataset(input_file_path)
    occurrences = compute_occurrences(dataset)
    occurrences_with_totals = add_model_totals(occurrences)
    sorted_results = sort_results(occurrences_with_totals)

    save_to_tsv(sorted_results, output_file_path)


if __name__ == "__main__":
    main()
