#This module provides regular expression matching 
import re 


def norm_temp(input) :
    '''Returns the normalized value of a temperature 
    Parameters:
    input (str): The raw value of the temperature

    Returns:
    str: The normalized value of the input
    '''
    input = input.lower() #We convert the input to lowercase
    temp = re.search(r"([0-9]+)(\.*[0-9]+)?(.*)?", input) #Extraction of the temperature and unit with a regex and the search method of the re module 
    unit = 'k' # setting the default unit to k (kelvin)

    #Fetching the temperature value and casting to int or float     
    if temp.group(2) != None :
        value = (float) (temp.group(1)+temp.group(2).strip())
    else : 
         value = (int) (temp.group(1))

    #Fetching the unit and converting to kelvin when needed 
    if temp.group(3) != None :
        unit = temp.group(3)
        unit = unit.strip(' ') #We remove the spaces around the unit if there are any
        unit = unit.strip('°') #We remove the degree symbol if there is one
        if unit == '' : #if there is no unit we assume it's kelvin
            unit= 'k'
        elif 'c' in unit : # if the unit is in celsius we convert it to kelvin 
            value += 273.15
            unit = 'k'
    
    temp_norm = (str)(value)+unit #We build the output string
    return temp_norm


if __name__ == "__main__":
    test = ["300", "300 k", "27", "300k", "0c", "37 celsius", "37°C", "310.15°K", "20 Celsius" ] #Testing different cases of temp normalisation
    for t in test : 
        print(f"norm_temp('{t}') = {norm_temp(t)}")

            
    
            
            
            
            
        
    


