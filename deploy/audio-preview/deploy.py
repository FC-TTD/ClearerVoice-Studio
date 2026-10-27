"""Snapshot and deploy only this isolated ClearVoice preview on edge; no existing service changes."""
from pathlib import Path
import hashlib,json,shutil,subprocess,tarfile,tempfile
root=Path(__file__).resolve().parents[2]
files=[p for p in (root/'clearvoice/clearvoice').rglob('*') if p.is_file() and p.suffix in ['.py','.yaml','.yml','.json','.txt']]
files += [p for p in (root/'deploy/audio-preview').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
for p in files:
 if str(p.relative_to(root)).startswith('clearvoice/clearvoice/'):
  assert subprocess.check_output(['git','-C',str(root),'show','6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61:'+str(p.relative_to(root))])==p.read_bytes()
release='h-'+hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
remote='/opt/clearvoice-audio-preview/releases/'+release
with tempfile.TemporaryDirectory() as temporary:
 folder=Path(temporary)
 for p in files:
  target=folder/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 shutil.copy2(root/'deploy/audio-preview/Dockerfile',folder/'Dockerfile')
 shutil.copy2(root/'deploy/audio-preview/compose.yaml',folder/'compose.yaml')
 shutil.copy2(root/'deploy/audio-preview/.dockerignore',folder/'.dockerignore')
 (folder/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(folder/'.env').write_text('AUDIO_RELEASE='+release+'\n')
 archive=folder/'bundle.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for p in folder.iterdir():
   if p!=archive:tar.add(p,arcname=p.name,filter=lambda t:None if '__pycache__' in t.name else t)
 subprocess.run(['ssh','-o','BatchMode=yes','root@ttd-edge','mkdir -p '+remote],check=True)
 subprocess.run(['scp','-q',str(archive),'root@ttd-edge:'+remote+'/'],check=True)
cmd=r'''
set -euo pipefail
cd "$1"
tar -xzf bundle.tar.gz
python3 - <<'CHECK'
import json,subprocess,ipaddress
from pathlib import Path
for target in ['/mnt/TTD','/mnt/TTD-Data']:
 assert subprocess.check_output(['findmnt','-T',target,'-n','-o','FSTYPE'],text=True).strip().startswith('nfs')
assert Path('/mnt/TTD/04_应用/pymss-ui-preview/jobs').is_dir()
assert Path('/mnt/TTD-Data/clearvoice-audio-preview/models-lock.json').is_file()
network=ipaddress.ip_network('10.41.0.0/24')
ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split()
for n in json.loads(subprocess.check_output(['docker','network','inspect',*ids])):
 if n['Name']=='clearvoice-audio-preview_default':continue
 for c in n.get('IPAM',{}).get('Config') or []:
  if c.get('Subnet') and ':' not in c['Subnet']:assert not network.overlaps(ipaddress.ip_network(c['Subnet'])),n['Name']
for r in json.loads(subprocess.check_output(['ip','-j','-4','route'])):
 if r.get('dst','default')=='default' or r.get('dev','').startswith(('br-','docker')):continue
 assert not network.overlaps(ipaddress.ip_network(r['dst'],strict=False))
print('NAS and explicit non-overlapping network verified.')
CHECK
mkdir -p /mnt/TTD/04_应用/clearvoice-audio-preview
touch /mnt/TTD/04_应用/clearvoice-audio-preview/.maintenance
trap 'rm -f /mnt/TTD/04_应用/clearvoice-audio-preview/.maintenance' EXIT
if docker inspect clearvoice-audio-preview >/dev/null 2>&1; then
 test "$(docker inspect clearvoice-audio-preview --format '{{index .Config.Labels "ttd.preview.owner"}}')" = ClearerVoice-Studio
 test "$(docker exec clearvoice-audio-preview python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['busy'])")" = False
 if docker top clearvoice-audio-preview -eo args | grep -Eq 'audio_api[.]worker|qa-inputs/(smoke|ss-quality)[.]py'; then
  echo 'Owned inference or smoke is active; finish it before deployment.' >&2; exit 5
 fi
 docker inspect clearvoice-audio-preview > previous-container.json
else
 test -z "$(ss -H -ltn sport = :17902)"
fi
base=sha256:ff9a24184aa1a62e32918c6f032c7e87896ee94a34e0721754e93f73d3d91008
if docker image inspect clearvoice-audio-base:h-ff9a24184aa1 >/dev/null 2>&1; then
 test "$(docker image inspect clearvoice-audio-base:h-ff9a24184aa1 --format '{{.Id}}')" = "$base"
else
 docker image inspect "$base" >/dev/null
 docker tag "$base" clearvoice-audio-base:h-ff9a24184aa1
fi
mkdir -p /mnt/TTD/04_应用/clearvoice-audio-preview
ip route get 192.168.32.214 > home-route-before.txt
docker build --network none --pull=false -t clearvoice-audio-preview:"$2" . > build.log 2>&1
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f compose.yaml up -d --no-build --pull never
ip route get 192.168.32.214 > home-route-after.txt
docker inspect clearvoice-audio-preview --format '{{.Image}} {{.State.Status}}'
'''
subprocess.run(['ssh','-o','BatchMode=yes','root@ttd-edge','bash','-s','--',remote,release],input=cmd,text=True,check=True)
print('ClearVoice preview:',release,remote)
