"""v1: Original continuous instrumental and timed packing effects; no speech."""
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
r=Path(__file__).resolve().parent;sr=48000;duration=1042/30;n=round(sr*duration)
rng=np.random.default_rng(1742);music=np.zeros((n,2));sfx=np.zeros((n,2));beat=60/128
def place(dst,at,x,pan=0,gain=1):
    k=round(at*sr)
    if k>=n:return
    x=x[:n-k];dst[k:k+len(x)]+=gain*x[:,None]*np.array([np.sqrt((1-pan)/2),np.sqrt((1+pan)/2)])
def tone(m,d,decay,harm=.2):
    t=np.arange(round(sr*d))/sr;f=440*2**((m-69)/12)
    return (np.sin(2*np.pi*f*t)+harm*np.sin(4*np.pi*f*t))*np.minimum(t/.008,1)*np.exp(-decay*t)*np.minimum((d-t)/.025,1)
def noise(d,lo,hi):
    return signal.sosfilt(signal.butter(2,[lo,hi],fs=sr,btype='bandpass',output='sos'),rng.normal(0,.6,round(sr*d)))
for k in range(int(duration/beat)+1):
    at=k*beat;root=[50,46,53,48][(k//8)%4];t=np.arange(round(sr*.25))/sr
    if k%4 in (0,2):place(music,at,np.sin(2*np.pi*(46*t+2.4*(1-np.exp(-36*t))))*np.exp(-19*t),gain=.60)
    if k%4 in (1,3):place(music,at,noise(.25,900,7000)*np.exp(-26*t),.1,.35)
    for off in [0,.5]:
        tt=np.arange(round(sr*.08))/sr
        place(music,at+off*beat,noise(.08,7000,16000)*np.exp(-60*tt),.35 if off else -.35,.14)
    if k%4 in (0,2,3):place(music,at,tone(root-12,.40,6,.24),gain=.43)
    for note,off in zip(([12,19] if k%2==0 else [15,22]),(.25,.75)):
        x=tone(root+note,.32,10)
        place(music,at+off*beat,x,-.3 if k%2 else .3,.19)
        place(music,at+off*beat+.15,x,.5,.035)
# Gentle carton contacts and tape pulls, without invented voices.
for at in [1.1,2.5,4.6,6.0,8.8,10.2,11.4,13.2,15.1,17.7,19.5,21.4,23.5,25.8,27.6,29.3,30.3,31.0]:
    t=np.arange(round(sr*.16))/sr
    x=noise(.16,150,2500)*np.exp(-28*t)+.2*np.sin(2*np.pi*100*t)*np.exp(-32*t)
    place(sfx,at,x,(-.2 if int(at)%2 else .2),.3)
for at,d in [(3.6,.48),(13.5,.45),(31.7,.6)]:
    t=np.arange(round(sr*d))/sr;env=np.sin(np.pi*t/d)**.6
    place(sfx,at,noise(d,1000,8500)*env*(.6+.4*np.sin(2*np.pi*30*t)**2),.1,.23)
for at in [5.5,15.0]:
    d=.22;t=np.arange(round(sr*d))/sr
    place(sfx,at-.1,noise(d,700,6000)*np.sin(np.pi*t/d)**2,0,.17)
for m in [74,78,81]:place(sfx,32.85,tone(m,.8,4),0,.1)
t=np.arange(n)/sr;fade=np.minimum(1,t/.05)*np.clip((duration-t)/.45,0,1)
music*=fade[:,None]*.65;sfx*=fade[:,None]
mix=music+sfx;peak=np.max(np.abs(mix));mix*=min(1,.84/peak)
for name,x in [('bgm',music),('sfx',sfx),('mix',mix)]:wavfile.write(r/(name+'.wav'),sr,(np.clip(x,-1,1)*32767).astype('int16'))
print('Original 128 BPM instrumental + packing effects:',duration,'seconds; no narration or lyrics.')
