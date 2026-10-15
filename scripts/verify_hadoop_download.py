import hashlib,re,sys
from pathlib import Path
expected=re.search(r'\b[a-fA-F0-9]{128}\b',Path(sys.argv[2]).read_text()).group(0).lower()
h=hashlib.sha512()
with open(sys.argv[1],'rb') as f:
    for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
if h.hexdigest()!=expected:raise SystemExit('Hadoop checksum mismatch')
print('Hadoop SHA512 verified')
