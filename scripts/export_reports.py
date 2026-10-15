"""Merge Spark part files into stable Tableau CSV sources (local output)."""
import csv, os
from pathlib import Path
raw=os.getenv('LOCAL_CURATED_DIR','data/curated')
root=Path(raw)
for folder in root.iterdir():
    parts=sorted(folder.glob('part-*.csv')) if folder.is_dir() else []
    if not parts: continue
    with (root/(folder.name+'.csv')).open('w',newline='') as out:
        writer=None
        for part in parts:
            with part.open(newline='') as source:
                reader=csv.DictReader(source)
                if writer is None: writer=csv.DictWriter(out,fieldnames=reader.fieldnames,lineterminator='\n'); writer.writeheader()
                writer.writerows(reader)
