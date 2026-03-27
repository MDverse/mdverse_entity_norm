import requests
import re


grounding = requests.post('http://grounding.indra.bio/ground', json={'text': 'kras'})
if grounding.status_code == 200 :
    print(f"grounding : {grounding}")


with open ("MOL.txt") as f :
    for line in f :
        potential_PDB = line.strip()
        if potential_PDB[0].isnumeric() and len(potential_PDB) == 4 : 
            response = requests.get(f"https://data.rcsb.org/rest/v1/core/entry/{potential_PDB}")
            if response.status_code == 200 :
                print(f"Depuis PDB : {potential_PDB}")
        else : 
            potentiel_UNIPROT = re.search("([O,P,Q][0-9][A-Z,0-9][A-Z,0-9][A-Z,0-9][0-9])", line)
            if potentiel_UNIPROT is not None :
                print(f"Depuis UNIPROT : {potentiel_UNIPROT}")
            potentiel_UNIPROT = re.search("([A-N,R-Z][0-9][A-Z][A-Z,0-9][A-Z,0-9][0-9])", line)
            if potentiel_UNIPROT is not None :
                print(f"Depuis UNIPROT : {potentiel_UNIPROT}")
            potentiel_UNIPROT = re.search("([A-N,R-Z][0-9][A-Z][A-Z,0-9][A-Z,0-9][0-9][A-Z][A-Z,0-9][A-Z,0-9][0-9])", line)
            if potentiel_UNIPROT is not None :
                print(f"Depuis UNIPROT : {potentiel_UNIPROT.group(1)}")
          