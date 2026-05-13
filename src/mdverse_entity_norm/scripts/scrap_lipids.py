import httpx
import pandas as pd
from bs4 import BeautifulSoup

URL = "https://charmm-gui.org/?doc=archive&lib=csml"

page = httpx.get(URL)
soup = BeautifulSoup(page.content, "html.parser")


def get_lipid_family_name(th):
    """Return the family name from a <th class='header'> tag."""
    bold_tag = th.find("b")
    if bold_tag:
        return bold_tag.get_text(strip=True)
    return None


def parse_data_row(row, current_family):
    """Extract short name and long name from a data row, or return None."""
    cells = row.find_all("td")
    if len(cells) < 2:
        return None

    short_name = cells[0].get_text(strip=True)
    if not short_name:
        return None

    # Long name is inside a <font> tag inside cells[1]
    font_tag = cells[1].find("font")
    long_name = (
        font_tag.get_text(strip=True) if font_tag else cells[1].get_text(strip=True)
    )

    return {
        "family": current_family,
        "short_name": short_name,
        "long_name": long_name,
    }


def scrape_table(soup):
    results = []

    for header_th in soup.find_all("th", class_="header"):
        current_family = get_lipid_family_name(header_th)
        if not current_family:
            continue
        tbody = header_th.find_next_sibling("tbody")
        if not tbody:
            continue

        for row in tbody.find_all("tr"):
            entry = parse_data_row(row, current_family)
            if entry:
                results.append(entry)

    return results


def print_preview(results, n=15):
    """Print the first n rows to the terminal."""
    print(f"Found {len(results)} residues/lipids\n")
    print(f"{'Family':<30} {'Short':^8}  Long name")
    print("-" * 80)
    for r in results[:n]:
        print(f"{r['family']:<30} {r['short_name']:^8}  {r['long_name'][:40]}")


def save_to_csv(results, filename="csml_lipids.csv"):
    """Save the results list to a CSV file using pandas."""
    df = pd.DataFrame(results)
    df.to_csv(filename, index=False)
    print(f"\nSaved {len(results)} rows to '{filename}'")


def main():
    results = scrape_table(soup)
    print_preview(results)
    save_to_csv(results)


if __name__ == "__main__":
    main()
