import json

def load_candidates(file_path, limit=None):
    
    count = 0;
    
    with open(file_path, "r", encoding="utf-8"  ) as f:
       
        for line in f:
            if limit is not None and count >= limit:
                break
            
            try : 

            
                count += 1
                yield json.loads(line)
            
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON on line {count}: {e}")
                
                
            