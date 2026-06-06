#ranks candidates based on their scores and returns the top 500 candidates per batch

import heapq
from multiprocessing import Pool

from batch import create_batches
from score_computer import score

def process_batch(batch):
    
    top500 = []
    
    for candidate in batch:
        
        candidate_score = score(candidate)
        
        if len(top500) < 500:
            heapq.heappush(top500, (candidate_score, candidate))
        elif candidate_score > top500[0][0]:
            heapq.heappushpop(top500, (candidate_score, candidate))
            
    return top500

