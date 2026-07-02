#ranks candidates based on their scores and returns the top 500 candidates per batch

from multiprocessing import Pool
import heapq


from .batch import create_batches
from .score_computer import score

def process_batch(batch, weights=None):

    top500 = []

    for idx, candidate in enumerate(batch):          # idx = unique tiebreaker

        candidate_score = score(candidate, weights)

        if len(top500) < 500:
            heapq.heappush(top500, (candidate_score, idx, candidate))
        elif candidate_score > top500[0][0]:
            heapq.heappushpop(top500, (candidate_score, idx, candidate))

    return top500


def run_ranking(file_path, weights=None):
    
    batches = create_batches(file_path, num_batches=4)
    
    from functools import partial
    worker = partial(process_batch, weights=weights)
    with Pool(processes=4) as pool:
        results = pool.map(worker, batches)
    
    
    return merge_results(results, top_n=100)


def merge_results(batch_results, top_n=100):

    merged = sorted(
        (item for batch in batch_results for item in batch),
        key=lambda x: x[0],
        reverse=True,
    )

    # Strip the tiebreaker index; return (score, candidate) pairs
    return [(score, candidate) for score, _idx, candidate in merged[:top_n]]




#multiprocessing safety guard, prevents infinite spawning of processes on Windows

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    top100 = run_ranking(sys.argv[1])
    print(f"Top {len(top100)} candidates ranked successfully.")
 
