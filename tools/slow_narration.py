"""Slow the Module I-1 narration by 10% and make the voice clearer.
Usage: python3 improve_narration.py <course folder>
Works on the original-speed files: formant-preserving time stretch, voice EQ,
gentle compression, loudness normalized to -16 LUFS, 44.1 kHz 128 kbps."""
import glob, os, re, subprocess, sys
R = 0.9
os.chdir(sys.argv[1])
CHAIN = ','.join([
    'aresample=44100:resampler=soxr',
    'rubberband=tempo=%s:pitch=1:formant=preserved:pitchq=quality:transients=smooth:detector=soft:window=long' % R,
    'highpass=f=75',
    'equalizer=f=250:t=q:w=1.0:g=-2.5',
    'equalizer=f=3200:t=q:w=1.2:g=3',
    'treble=g=2:f=6500',
    'acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=1',
    'loudnorm=I=-16:TP=-1.5:LRA=9',
    'aresample=44100',
])
for f in sorted(glob.glob('assets/narration/*.mp3')):
    tmp = f + '.tmp.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-af', CHAIN, '-ar', '44100', '-ac', '1',
                    '-c:a', 'libmp3lame', '-b:a', '128k', tmp], check=True)
    os.replace(tmp, f)
# provisional caption timing: scale to the new speed (align_captions.py refines it)
def scale(m):
    t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) / R
    return '%02d:%02d:%06.3f' % (t // 3600, t % 3600 // 60, t % 60)
for f in glob.glob('assets/narration/*.vtt'):
    s = open(f).read()
    open(f, 'w').write(re.sub(r'(\d\d):(\d\d):(\d\d\.\d{3})', scale, s))
def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout)
def fix(m):
    tag = m.group(0)
    sid = re.search(r'narration/([^"]+)\.mp3', tag).group(1)
    d = dur('assets/narration/%s.mp3' % sid)
    tag = re.sub(r'data-duration="[\d.]+"', 'data-duration="%.2f"' % d, tag)
    return re.sub(r'this screen, \d+ seconds', 'this screen, %d seconds' % round(d), tag)
h = open('index.html').read()
open('index.html', 'w').write(re.sub(r'<audio[^>]*>', fix, h))
print('narration slowed and clarified')
