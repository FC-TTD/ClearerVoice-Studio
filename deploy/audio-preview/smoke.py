"""Real native CUDA smoke. Fixtures are private QA assets, never UI demos."""
import json,subprocess,sys,uuid,itertools
from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
from audio_api.common import DATA,SPECS,model_row,key,write
from audio_api.worker import resample
qa=DATA/'qa-inputs'
def mono(path,sr):
 a,old=sf.read(path,dtype='float32',always_2d=True);a=a.mean(1)
 return resample(a,old,sr) if old!=sr else a
s1=mono(qa/'speech1.wav',16000);s2=mono(qa/'speech2.wav',16000);n=min(len(s1),len(s2),192000);s1=s1[:n];s2=s2[:n]
s1=s1/(np.std(s1)+1e-9)*.06;s2=s2/(np.std(s2)+1e-9)*.06
mix=s1+s2;sf.write(qa/'overlap.wav',mix,16000,subtype='FLOAT');sf.write(qa/'reference-a.wav',s1,16000,subtype='FLOAT');sf.write(qa/'reference-b.wav',s2,16000,subtype='FLOAT')
low=mono(qa/'input_sr.wav',16000)[:96000];sf.write(qa/'bandlimited.wav',low,16000,subtype='FLOAT')
clean=mono(qa/'speech1.wav',48000)[:288000];clean=clean/(np.std(clean)+1e-9)*.06
noisy=clean+np.random.default_rng(20261026).normal(0,.02,len(clean)).astype('float32');sf.write(qa/'noisy.wav',noisy,48000,subtype='FLOAT')
verified={};report={};write(DATA/'verified-models.json',{})
for name,(task,sr,stems) in SPECS.items():
 source=qa/('overlap.wav' if task=='speech_separation' else 'bandlimited.wav' if task=='speech_super_resolution' else 'noisy.wav')
 folder=DATA/'smoke'/name;folder.mkdir(parents=True,exist_ok=True);path=folder/'job.json'
 state=dict(id='cv-'+uuid.uuid4().hex,model='cv:'+name,stems=[k for k,v in stems],input=str(source),status='queued',outputs=[],filename=source.name)
 write(path,state)
 with (folder/'native-inference.log').open('w') as log:
  rc=subprocess.run([sys.executable,'-m','audio_api.worker',str(path)],stdout=log,stderr=log,timeout=600).returncode
 state=json.loads(path.read_text());ok=not rc and state['status']=='succeeded' and len(state['outputs'])==len(stems)
 if ok:
  for out in state['outputs']:
   info=sf.info(folder/out['file']);assert info.samplerate==48000 and info.subtype=='PCM_24' and abs(info.duration-sf.info(source).duration)<.001
   arr=sf.read(folder/out['file'],dtype='float32')[0];assert np.isfinite(arr).all() and np.max(np.abs(arr))>1e-8
 verified[name]=dict(passed=ok,key=key(model_row(name)),outputs=state['outputs'],peak_cuda_bytes=state.get('peak_cuda_bytes',0))
 report[name]=dict(passed=ok,error=state.get('error',''),seconds=state.get('seconds'),peak_cuda_bytes=state.get('peak_cuda_bytes'),outputs=state['outputs'])
 print(name,json.dumps(report[name]),flush=True)
 if not ok:print((folder/'native-inference.log').read_text()[-4500:],flush=True)
write(DATA/'smoke-report.json',report)
assert all(v['passed'] for v in verified.values()),'Some models failed actual inference; do not mark them usable.'
# Objective separation evidence on this two-speaker fixture; not a Chinese listening acceptance.
def sisdr(x,y):
 x=x-x.mean();y=y-y.mean();target=np.dot(x,y)/(np.dot(y,y)+1e-12)*y
 return 10*np.log10((np.dot(target,target)+1e-12)/(np.dot(x-target,x-target)+1e-12))
folder=DATA/'smoke/MossFormer2_SS_16K';state=json.loads((folder/'job.json').read_text());out=[mono(folder/o['file'],16000)[:n] for o in state['outputs']]
base=(sisdr(mix,s1)+sisdr(mix,s2))/2
score=max((sisdr(out[i],s1)+sisdr(out[j],s2))/2 for i,j in [(0,1),(1,0)])
# Super-resolution must differ from plain sample-rate conversion and add high-frequency content.
folder=DATA/'smoke/MossFormer2_SR_48K';state=json.loads((folder/'job.json').read_text());enh=sf.read(folder/state['outputs'][0]['file'],dtype='float32')[0];plain=resample(low,16000,48000)[:len(enh)];enh=enh.reshape(-1)
frequencies=np.fft.rfftfreq(len(enh),1/48000);high=float(np.sum(np.abs(np.fft.rfft(enh))[frequencies>8000]**2));plain_high=float(np.sum(np.abs(np.fft.rfft(plain))[frequencies>8000]**2))
short=min(n,96000)
short_score=max((sisdr(out[i][:short],s1[:short])+sisdr(out[j][:short],s2[:short]))/2 for i,j in [(0,1),(1,0)])
checks=dict(first_overlap_sisdr_db=float(short_score),two_speaker_sisdr_db=float(score),mixture_sisdr_db=float(base),improvement_db=float(score-base),superres_difference_rms=float(np.sqrt(np.mean((enh-plain)**2))),superres_high_band_energy=high,resample_high_band_energy=plain_high,quality_listening='NOT_RUN',long_speaker_identity_acceptance='NOT_RUN')
assert short_score>5 and score>base, 'Active-overlap fixture did not separate from the original mixture.'
assert checks['superres_difference_rms']>1e-5 and high>plain_high*2, 'No verified model super-resolution beyond resampling.'
write(DATA/'verified-models.json',verified);write(DATA/'objective-smoke.json',checks);print(json.dumps(checks),flush=True)
