#Created to download the download the test data for the project.    Test data saved in https://drive.google.com/file/d/1aRToetVoRX02wVshEMxWLBmnu_HuQm--/view?usp=sharing 
import os
import subprocess
import sys


def download_dataset():
    try:
      import gdown
    
    except ImportError:
      print("Installing gdown")
      subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "gdown"]
         )
    import gdown

   FILE_ID = "1aRToetVoRX02wVshEMxWLBmnu_HuQm--"
   OUTPUT = "temp/candidates.jsonl"

   os.makedirs("temp", exist_ok=True)

    if not os.path.exists(OUTPUT):
      print("Downloading dataset")
      gdown.download(
         f"https://drive.google.com/uc?id={FILE_ID}",
         OUTPUT,
         quiet=False
        )
    else:
     print("Dataset already exists.")

    print("Ready.")

    return OUTPUT



#To be deleted before submission. 
