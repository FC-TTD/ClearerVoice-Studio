"""Pin author metadata; reuse matching local weights, otherwise download on the GPU host."""
import json,hashlib,subprocess,shutil
from pathlib import Path
NAMES=['MossFormer2_SS_16K','MossFormer2_SR_48K','MossFormer2_SE_48K','FRCRN_SE_16K','MossFormerGAN_SE_16K']
root=Path('/mnt/TTD-Data/clearvoice-audio-preview');root.mkdir(parents=True,exist_ok=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 return h.hexdigest()
rows=json.loads(Path(__file__).with_name('models-lock.json').read_text())
assert [r['name'] for r in rows]==NAMES
for row in rows:
 name=row['name'];folder=root/'checkpoints'/name;folder.mkdir(parents=True,exist_ok=True)
 for art in row['artifacts']:
  target=folder/art['file'];old=Path('/opt/clearervoice-studio/checkpoints')/name/art['file']
  if not target.exists() and old.is_file() and old.stat().st_size==art['bytes'] and sha(old)==art['sha256']:shutil.copy2(old,target)
  if not target.exists():
   partial=target.with_suffix(target.suffix+'.partial')
   for host in ['https://hf-mirror.com','https://huggingface.co']:
    rc=subprocess.run(['curl','-fL','--retry','2','--connect-timeout','15','--max-time','1200','-C','-','-o',str(partial),f"{host}/alibabasglab/{name}/resolve/{row['revision']}/{art['file']}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
    if rc==0 and partial.stat().st_size==art['bytes'] and sha(partial)==art['sha256']:partial.rename(target);break
   else:raise RuntimeError('Download failed: '+name+'/'+art['file'])
  assert target.stat().st_size==art['bytes'] and sha(target)==art['sha256'],name+'/'+art['file']
 print('READY',name,sum(a['bytes'] for a in row['artifacts']),flush=True)
temporary=root/'models-lock.tmp';temporary.write_text(json.dumps(rows,indent=2)+'\n');temporary.replace(root/'models-lock.json')
