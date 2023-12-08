import csv
import os

def data2csv(data:list, output:str)->bool:
    """ Gets the data arg and turn it into a csv file

    Args:
        data (list):A list of dictionaries with the same keys, such as [{'key1': 0, 'key2': 1}, ..., {'key1': 3, 'key2': 4}].
        output (str): The path to save the csv file.
    Returns:
        bool: True if the CSV file is successfully saved.
    """      
    try:
        _data_header = data[0].keys( ) #get keys from first data element
        directory_name, filename = os.path.split(output)
        with open(output, 'w', newline='') as csvFile:
            writer = csv.DictWriter(csvFile, fieldnames=_data_header)

            writer.writeheader()
            writer.writerows(data)                        
            csvFile.close()

        print(f"{filename} saved in {directory_name}")

        return True
    except:
        return False