from candidate_loader import load_candidates
from scripts.Test_data import download_dataset
from batch import create_batches

#Loads the candidates(file_name,limit)
FILE_PATH = download_dataset()

#for candidate in load_candidates(FILE_PATH, limit=1):
  #  print(candidate["profile"])

batches = create_batches(FILE_PATH)

print(batches)