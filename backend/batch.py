#To make batches of candidates for parallel processing

from .candidate_loader import load_candidates

def create_batches(file_path, num_batches = 4):
    
    candidates = list(load_candidates(file_path, limit=None))
    batch_size = len(candidates) // num_batches
    
    batches = []
    
    for i in range(num_batches):
        
        start = i * batch_size
        
        if i == num_batches - 1:
            end = len(candidates)
        else:
            end = start + batch_size
            
        batches.append(candidates[start:end])
        
    return batches    
            