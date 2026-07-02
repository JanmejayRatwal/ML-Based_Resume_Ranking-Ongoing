# output_writer.py — Saves the ranked results to a CSV file

import csv
import os

def write_output(top100, filename="output.csv", explanations=None):
    """
    Writes the top-ranked candidates to a CSV file.

    Args:
        top100   : list of (score, candidate_dict) tuples from merge_results()
        filename : output file path (relative or absolute)
        explanations : optional list of explanation strings (one per candidate)
    """
    # Make sure the output directory exists if a path was given
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header row
        if explanations:
            writer.writerow(["rank", "candidate_id", "score", "name", "location", "years_exp", "explanation"])
        else:
            writer.writerow(["rank", "candidate_id", "score", "name", "location", "years_exp"])

        for rank, (score, candidate) in enumerate(top100, start=1):
            profile = candidate.get("profile", {}) or {}
            row = [
                rank,
                candidate.get("candidate_id", ""),
                f"{score:.4f}",
                profile.get("anonymized_name", ""),
                profile.get("location", ""),
                profile.get("years_of_experience", ""),
            ]
            
            # Add explanation if provided
            if explanations and rank - 1 < len(explanations):
                row.append(explanations[rank - 1])
            
            writer.writerow(row)
