"""Native ClearVoice CUDA inference; one child exits after each file, no offload."""
import json,sys,time,traceback,hashlib,fcntl
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from .common import DATA,SPECS,model_row,write

def resample(audio,old,new):
 from math import gcd
 d=gcd(old,new);return resample_poly(audio,new//d,old//d,axis=-1).astype('float32')
def separate_speakers(instance,mix,sr):
 # Native 2-second decoding can permute speakers between very short windows.
 # Use native full-window inference with bounded 8-second context, then align
 # overlapping predictions by waveform similarity. No speaker identity claim.
 instance.models[0].args.one_time_decode_length=20.
 length=mix.shape[-1];window=8*sr;hop=6*sr
 if length<=window:return instance(mix)
 output=np.zeros((2,length),dtype='float32');weights=np.zeros(length,dtype='float32')
 def correlation(x,y):return float(np.dot(x,y)/(np.linalg.norm(x)*np.linalg.norm(y)+1e-12))
 for start in range(0,length,hop):
  stop=min(start+window,length);chunk=instance(mix[:,start:stop]);current=np.stack([np.asarray(v).reshape(-1)[:stop-start] for v in chunk])
  count=stop-start;overlap=min(window-hop,count) if start else 0
  if overlap:
   previous=output[:,start:start+overlap]/np.maximum(weights[start:start+overlap],1e-8)
   direct=sum(abs(correlation(previous[i],current[i,:overlap])) for i in range(2))
   swapped=sum(abs(correlation(previous[i],current[1-i,:overlap])) for i in range(2))
   if swapped>direct:current=current[::-1].copy()
   for i in range(2):
    if correlation(previous[i],current[i,:overlap])<-.1:current[i]*=-1
  fade=np.ones(count,dtype='float32')
  if overlap:fade[:overlap]=np.linspace(0,1,overlap)
  if stop<length:fade[-(window-hop):]=np.linspace(1,0,window-hop)
  output[:,start:stop]+=current*fade;weights[start:stop]+=fade
  if stop==length:break
 return [a[None,:] for a in output/np.maximum(weights,1e-8)]

def run(path):
 state=json.loads(path.read_text());started=time.time()
 try:
  import torch
  if not torch.cuda.is_available():raise RuntimeError('GPU暂不可用，已上传音频会保留。')
  torch.cuda.set_device(0)
  name=state['model'].removeprefix('cv:');task,sr,labels=SPECS[name];row=model_row(name)
  if not row:raise RuntimeError('模型尚未准备完成。')
  for art in row['artifacts']:
   source=Path('/models/checkpoints')/name/art['file']
   if not source.is_file() or source.stat().st_size!=art['bytes']:raise RuntimeError('模型文件缺失或不完整。')
  state.update(status='running',message='正在加载 ClearVoice 模型…');write(path,state)
  audio,original_sr=sf.read(state['input'],dtype='float32',always_2d=True)
  if name=='MossFormer2_SR_48K' and original_sr<16000:raise RuntimeError('此超分模型适用于16 kHz及以上的低带宽人声；当前音频采样率过低，请先试听降噪模型。')
  mix=audio.mean(axis=1)[None,:] if task=='speech_separation' else audio.T
  if original_sr!=sr:mix=resample(mix,original_sr,sr)
  expected=mix.shape[-1]
  # The SR vocoder operates on 256-sample hops. Pad the input context, then trim
  # the generated output back to the exact original duration, never pad output.
  if task=='speech_super_resolution':mix=np.pad(mix,((0,0),(0,1024+(-expected)%256)))
  from clearvoice import ClearVoice
  from clearvoice.networks import SpeechModel
  # The container has one assigned GPU. Native auto-selection uses host ordinals;
  # bind its logical selection to cuda:0 and reject any CPU fallback.
  SpeechModel.get_free_gpu=lambda self:0
  loaded=[]
  def strict_load(self,model,checkpoint_path,model_key=None):
   checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=True)
   source=checkpoint.get(model_key,checkpoint) if model_key else checkpoint
   mapped={}
   for target,value in model.state_dict().items():
    candidate=next((source[k] for k in [target,target.removeprefix('module.'),'module.'+target] if k in source and source[k].shape==value.shape),None)
    if candidate is None:raise RuntimeError('模型参数与官方权重不匹配，停止处理。')
    mapped[target]=candidate
   model.load_state_dict(mapped,strict=True);loaded.append(len(mapped))
  SpeechModel._load_model=strict_load
  instance=ClearVoice(task=task,model_names=[name])
  if instance.models[0].device.type!='cuda':raise RuntimeError('模型未使用已分配的GPU，停止处理。')
  state.update(message='正在分离两人对白…' if task=='speech_separation' else '正在补充人声高频细节…' if task=='speech_super_resolution' else '正在降低人声背景噪声…');write(path,state)
  with torch.inference_mode():raw=separate_speakers(instance,mix.astype('float32'),sr) if task=='speech_separation' else instance(mix.astype('float32'))
  if task=='speech_separation':
   if len(raw)!=2:raise RuntimeError('双人分离未返回两条说话人轨。')
   signals=list(raw)
  else:signals=[raw]
  outputs=[]
  for (stem,label),value in zip(labels,signals):
   if stem not in state['stems']:continue
   if isinstance(value,torch.Tensor):value=value.detach().float().cpu().numpy()
   arr=np.asarray(value,dtype='float32')
   if arr.ndim==1:arr=arr[None,:]
   if arr.ndim!=2 or arr.shape[-1]<expected or not np.isfinite(arr).all():raise RuntimeError('模型返回的音频无效或不完整。')
   arr=arr[...,:expected]
   if sr!=48000:arr=resample(arr,sr,48000)
   target=path.parent/(hashlib.sha256(stem.encode()).hexdigest()[:16]+'.wav')
   sf.write(target,arr.T,48000,subtype='PCM_24')
   outputs.append(dict(stem=stem,label=label,file=target.name,frames=arr.shape[-1],sample_rate=48000,channels=arr.shape[0]))
  if not outputs:raise RuntimeError('请选择模型支持的输出音轨。')
  state.update(status='succeeded',message='处理完成',outputs=outputs,error='',seconds=round(time.time()-started,2),peak_cuda_bytes=torch.cuda.max_memory_allocated(),native_sample_rate=sr,weight_tensors_verified=sum(loaded))
 except Exception as e:
  traceback.print_exc();state.update(status='failed',error=str(e),outputs=[])
 write(path,state)
if __name__=='__main__':
 with (DATA/'gpu-worker.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);run(Path(sys.argv[1]))
